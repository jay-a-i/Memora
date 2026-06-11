import os
import tempfile
from psycopg_pool import ConnectionPool
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import UploadFile, File, Form
from langchain_openai import ChatOpenAI
from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter 

#.env, LLM, Embedder, API, Connection, System Prompt Initializations:-

load_dotenv()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8501",
        "https://memora-j.streamlit.app/"],                                                
    allow_methods=["*"],
    allow_headers=["*"],
)

llm = ChatOpenAI(
    model="openai/gpt-oss-120b:free",
    api_key=os.getenv("OPENROUTER_API_KEY"), 
    base_url="https://openrouter.ai/api/v1",
    streaming=True
)

embedder = NVIDIAEmbeddings(
  model="nvidia/nv-embed-v1", 
  api_key=os.getenv("NVIDIA_API_KEY"), 
  truncate="NONE", 
)

sm = SystemMessage(
    content="""
    You are Memora, a personal AI assistant.
    Use memory when relevant.
    Don't invent memories.
    When answering questions about documents, only use information from the provided context.
    If the answer is not in the context, say "I couldn't find that in the document" instead of guessing.
    """
)

pool = ConnectionPool(os.getenv("CBDB_URL"), min_size=5, max_size=10)

#DataBase Blocks:-
def user_info(conn, username):

    username = username.lower().strip()

    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
        user = cur.fetchone()

        if user:
            return user[0]
        
        cur.execute("INSERT INTO users (username) VALUES (%s) RETURNING id", (username,))
        conn.commit()
        return cur.fetchone()[0]

def create_session(conn, user_id, title="Untitled Chat"):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sessions (user_id, title)
            VALUES (%s, %s)
            RETURNING id
            """,
            (user_id, title)
        )

        session_id = cur.fetchone()[0]
        conn.commit()

        return session_id

def save_msg(conn, session_id, role, content, embedding, tokens=None):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO messages (session_id, role, content, embedding, tokens_used) VALUES (%s,%s,%s,%s,%s)",
                    (session_id, role, content, embedding, tokens))
        conn.commit()


def fetch_hybrid_memory(conn, session_id, query_embedding, recent_limit=10, semantic_limit=5):
    with conn.cursor() as cur:

        # Recent messages
        cur.execute(
            """
            SELECT role, content
            FROM messages
            WHERE session_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (session_id, recent_limit))

        recent = cur.fetchall()[::-1]

        # Semantic retrieval
        cur.execute(
            """
            SELECT role,
            content,
            embedding <=> %s::vector AS distance
            FROM messages
            WHERE session_id = %s
            ORDER BY distance
            LIMIT %s
            """,
            (query_embedding, session_id, semantic_limit))

        semantic = []
        for role, content, distance in cur.fetchall():

            if distance < 0.35:
                semantic.append(
                    (role, content)
                )

        seen = set() 
        combined = [] 
        for role, content in recent + semantic:
            if content not in seen:
                seen.add(content)
                combined.append((role, content)) 
        return combined
    
def rows_to_messages(rows):
    messages = []
    for role, content in rows:
        if role == "human":
            messages.append(HumanMessage(content=content))
        else:
            messages.append(AIMessage(content=content))
    return messages

def save_document(conn, user_id, filename):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO documents (user_id, filename) VALUES (%s, %s) RETURNING id",
            (user_id, filename)
        )
        conn.commit()
        return cur.fetchone()[0]

def save_chunks(conn, document_id, chunks, embeddings):
    with conn.cursor() as cur:
        for chunk, embedding in zip(chunks, embeddings):
            cur.execute(
                """INSERT INTO document_chunks 
                   (document_id, content, embedding, page_number)
                   VALUES (%s, %s, %s, %s)""",
                (document_id, chunk.page_content, embedding, 
                 chunk.metadata.get("page", 0))
            )
        conn.commit()

def fetch_relevant_chunks(conn, user_id, query_embedding, limit=8):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT dc.content
            FROM document_chunks dc
            JOIN documents d ON dc.document_id = d.id
            WHERE d.user_id = %s
            AND dc.embedding <=> %s::vector < 0.6
            ORDER BY dc.embedding <=> %s::vector
            LIMIT %s
            """,
            (user_id, query_embedding, query_embedding, limit)
        )
        return [row[0] for row in cur.fetchall()]

#Pydantic Models:-
class ChatRequest(BaseModel):
    session_id: int
    message: str

class ChatResponse(BaseModel):
    response : str
    session_id : int

class SessionRequest(BaseModel):
    username : str
    title : str | None = "Untitled Chat"

class DocumentResponse(BaseModel):
    document_id: int
    filename: str
    chunks_count: int


#API Endpoints:-
@app.get('/')
async def root():
    return {"message": "Memora API is running"}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/sessions")
def create_new_session(request: SessionRequest):
    with pool.connection() as conn:
        user_id = user_info(conn, request.username)
        session_id = create_session(conn, user_id, request.title)

        return {"session_id": session_id}

@app.get("/users/{username}/sessions")
def get_sessions(username: str):

    with pool.connection() as conn:

        user_id = user_info(conn, username)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, title
                FROM sessions
                WHERE user_id = %s
                ORDER BY created_at DESC
                """,
                (user_id,)
            )

            rows = cur.fetchall()

        return [{
            "id": row[0],
            "title": row[1]
            } for row in rows]

@app.get("/sessions/{session_id}/messages")
def load_messages(session_id: int):

    with pool.connection() as conn:

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role, content
                FROM messages
                WHERE session_id = %s
                ORDER BY created_at
                """,
                (session_id,))

            rows = cur.fetchall()

        return [{
            "role": role,
            "content": content    
            } for role, content in rows]

@app.post("/documents/upload", response_model=DocumentResponse)
async def upload_document(
    username: str = Form(...),
    file: UploadFile = File(...)
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files supported")
    
    try:
        # Save PDF temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        # Load and chunk
        loader = PyPDFLoader(tmp_path)
        docs = loader.load()
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
        chunks = splitter.split_documents(docs)

        # Embed all chunks
        texts = [chunk.page_content for chunk in chunks]
        embeddings = embedder.embed_documents(texts)

        # Save to database
        with pool.connection() as conn:
            user_id = user_info(conn, username)
            document_id = save_document(conn, user_id, file.filename)
            save_chunks(conn, document_id, chunks, embeddings)

        # Cleanup temp file
        os.unlink(tmp_path)

        return DocumentResponse(
            document_id=document_id,
            filename=file.filename,
            chunks_count=len(chunks)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents/{username}")
def get_documents(username: str):
    with pool.connection() as conn:
        user_id = user_info(conn, username)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, filename, uploaded_at
                FROM documents
                WHERE user_id = %s
                ORDER BY uploaded_at DESC
                """,
                (user_id,)
            )
            rows = cur.fetchall()
        return [{"id": r[0], "filename": r[1], "uploaded_at": str(r[2])} for r in rows]

@app.delete("/documents/{document_id}")
def delete_document(document_id: int):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM document_chunks WHERE document_id = %s", (document_id,))
            cur.execute("DELETE FROM documents WHERE id = %s", (document_id,))
            conn.commit()
    return {"message": "Document deleted"}

@app.post("/chat/stream")
async def stream_chat(request: ChatRequest):

    try:
        with pool.connection() as conn:
            query_embedding = embedder.embed_query(request.message)
            
            with conn.cursor() as cur:
                # Session validation
                cur.execute("SELECT user_id FROM sessions WHERE id = %s", (request.session_id,))
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Session not found")
                user_id = row[0]  # get user_id here at the same time
            
            memory_rows = fetch_hybrid_memory(conn, request.session_id, query_embedding)
            chat_history = rows_to_messages(memory_rows)
            doc_chunks = fetch_relevant_chunks(conn, user_id, query_embedding)
            
            # Add document context to system message
            if doc_chunks:
                doc_context = "\n\n".join(doc_chunks)
                doc_message = SystemMessage(content=f"Relevant information from user's documents:\n\n{doc_context}")
                messages = [sm] + chat_history + [doc_message] + [HumanMessage(content=request.message)]
            else:
                messages = [sm] + chat_history + [HumanMessage(content=request.message)]

            def generate():
                with pool.connection() as save_conn:

                    full_response = ""

                    for chunk in llm.stream(messages):
                        if chunk.content:
                            full_response += chunk.content
                            yield chunk.content

                    save_msg(save_conn, request.session_id, "human", request.message, query_embedding)
                    response_embedding = embedder.embed_query(full_response)
                    save_msg(save_conn, request.session_id, "ai", full_response, response_embedding)

            return StreamingResponse(generate(), media_type="text/plain")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 