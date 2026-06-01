import os
import psycopg
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langchain_openai import ChatOpenAI
from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings
from langchain_core.messages import AIMessage, HumanMessage

load_dotenv()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"]
)

llm = ChatOpenAI(
    model="openai/gpt-oss-120b:free",
    api_key=os.getenv("OPENROUTER_API_KEY"), 
    base_url="https://openrouter.ai/api/v1",
)

embedder = NVIDIAEmbeddings(
  model="nvidia/nv-embed-v1", 
  api_key=os.getenv("NVIDIA_API_KEY"), 
  truncate="NONE", 
)

conn = psycopg.connect(os.getenv("CBDB_URL"))

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


def get_or_create_session(conn, user_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM sessions WHERE user_id = %s ORDER BY created_at DESC LIMIT 1",
            (user_id,)
        )
        session = cur.fetchone()
        
        if session:
            return session[0]

        cur.execute(
            "INSERT INTO sessions (user_id, title) VALUES (%s, %s) RETURNING id",
            (user_id, "NEW_CHAT")
        )
        conn.commit()
        return cur.fetchone()[0]

def save_msg(conn, session_id, role, content, embedding, tokens=None):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO messages (session_id, role, content, embedding, tokens_used) VALUES (%s,%s,%s,%s,%s)",
                    (session_id, role, content, embedding, tokens))
        conn.commit()

def fetch_hybrid_memory(conn, user_id, query_embedding, recent_limit=10, semantic_limit=5):
    with conn.cursor() as cur:
   
        cur.execute(
            """SELECT m.role, m.content FROM messages m
               JOIN sessions s ON m.session_id = s.id
               WHERE s.user_id = %s 
               ORDER BY m.created_at DESC 
               LIMIT %s""",
            (user_id, recent_limit)
        )
        recent = cur.fetchall()[::-1]
        
       
        cur.execute(
            """SELECT m.role, m.content FROM messages m
               JOIN sessions s ON m.session_id = s.id
               WHERE s.user_id = %s
               ORDER BY m.embedding <=> %s::vector
               LIMIT %s""",
            (user_id, query_embedding, semantic_limit)
        )
        semantic = cur.fetchall()
    
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


class ChatRequest(BaseModel):
    username : str
    message : str

class ChatResponse(BaseModel):
    response : str
    session_id : int

@app.get('/')
async def root():
    return {"message": "Memora API is running"}

@app.post('/chat')
async def Web_chat(request: ChatRequest):

    try:
        user_id = user_info(conn, request.username)
        session_id = get_or_create_session(conn, user_id)

        query_embedding = embedder.embed_query(request.message)
        memory_rows = fetch_hybrid_memory(conn, user_id, query_embedding)        
        chat_history = rows_to_messages(memory_rows)
  
        messages = chat_history + [HumanMessage(content=request.message)]
        response = llm.invoke(messages)
        
        save_msg(conn, session_id, "human", request.message, query_embedding)
        response_embedding = embedder.embed_query(response.content)
        save_msg(conn, session_id, "ai", response.content, response_embedding)

        return ChatResponse(response=response.content, session_id=session_id)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))