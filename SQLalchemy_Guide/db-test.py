from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

connection_url = URL.create(
    drivername="postgresql+psycopg", 
    username="postgres",
    password="1234",         
    host="localhost",                 
    port=5432,
    database="Memora (Agentic RAG version)"
)


engine = create_engine(connection_url)

try:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version();"))
        print("SQLAlchemy successfully connected!")
        print(f"Server version: {result.scalar()}")
except Exception as e:
    print(f"Connection failed: {e}")
