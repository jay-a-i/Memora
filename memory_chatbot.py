import os
import psycopg
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings
from langchain_core.messages import AIMessage, HumanMessage

load_dotenv()

username = input("Please Enter Your Username:  ")

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

conn = psycopg.connect(os.getenv("DB_URL"))

def user_info(conn, username):
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

def fetch_hybrid_memory(conn, session_id, query_embedding, recent_limit=10, semantic_limit=5):
    with conn.cursor() as cur:
        cur.execute(
            """SELECT role, content FROM messages 
               WHERE session_id = %s 
               ORDER BY created_at DESC 
               LIMIT %s""",
            (session_id, recent_limit)
        )
        recent = cur.fetchall()[::-1]
        
        cur.execute(
            """SELECT role, content FROM messages
               WHERE session_id = %s
               ORDER BY embedding <=> %s::vector
               LIMIT %s""",
            (session_id, query_embedding, semantic_limit)
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

def chat(conn, username=username):
    
    user_id = user_info(conn, username)
    session_id = get_or_create_session(conn, user_id)
    
    while True:
        user_input = input("You: ")
        if user_input.lower() == "exit":
            break

        query_embedding = embedder.embed_query(user_input)
        
        memory_rows = fetch_hybrid_memory(conn, session_id, query_embedding)
        chat_history = rows_to_messages(memory_rows)
        
        messages = chat_history + [HumanMessage(content=user_input)]
        response = llm.invoke(messages)
        
        save_msg(conn, session_id, "human", user_input, query_embedding)
        response_embedding = embedder.embed_query(response.content)
        save_msg(conn, session_id, "ai", response.content, response_embedding)
        
        print(f"AI: {response.content}")

if __name__ == "__main__":
    chat(conn)
