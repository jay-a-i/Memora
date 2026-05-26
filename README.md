# Memora — A Chatbot That Actually Remembers You

Most chatbots forget everything the moment you close the tab. Memora doesn't.

Built with LangChain and PostgreSQL, Memora stores every conversation in a real database and uses semantic search to recall relevant memories — even from weeks ago. It's not just remembering the last few messages, it's understanding which past conversations are actually relevant to what you're asking right now.

## How the memory works

There are two layers:

**Recent memory** grabs your last 10 messages chronologically — the immediate context of your conversation.

**Semantic memory** searches your entire conversation history using vector embeddings and finds the 5 most relevant past messages based on meaning, not just recency.

Both layers are combined and deduplicated before being sent to the LLM. So if you told the bot your favorite color three weeks and 500 messages ago, it still knows — as long as your question is related enough to surface it.

## Tech stack

- **LangChain** — LLM orchestration
- **PostgreSQL + pgvector** — persistent storage and vector similarity search
- **NVIDIA nv-embed-v1** — text embeddings (4096 dimensions)
- **OpenRouter** — LLM API access
- **psycopg3** — PostgreSQL connection

## Database schema

Three tables — users, sessions, and messages. Messages store both the raw text and a 4096-dimensional embedding vector. This lets you query by recency (SQL ORDER BY) and by semantic relevance (pgvector cosine similarity) at the same time.

```sql
SELECT role, content FROM messages
WHERE session_id = %s
ORDER BY embedding <=> %s::vector
LIMIT 5;
```

## Setup

### Prerequisites
- Python 3.11+
- PostgreSQL with pgvector extension
- NVIDIA API key (for embeddings)
- OpenRouter API key (for LLM)

### Installation

```bash
git clone https://github.com/jay-a-i/memora.git
cd memora
pip install -r requirements.txt
```

### Environment variables

Create a `.env` file:

- OPENROUTER_API_KEY=your_key,
- NVIDIA_API_KEY=your_key

### Database setup

```sql
CREATE DATABASE chatbot_memory;
\c chatbot_memory
CREATE EXTENSION vector;

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    title TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES sessions(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding vector(4096),
    tokens_used INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Run

```bash
python memory_chatbot.py
```

Enter your username when prompted. If you've used the app before, it picks up your last session automatically.

## What makes this different from a regular chatbot

Most tutorial chatbots store messages in a Python list that disappears on exit. Some use LangChain's built-in memory classes which are fine for prototyping but not designed to scale. This project skips all of that and goes straight to a proper database-backed implementation with a custom schema — closer to how a production system would actually be built.

The hybrid retrieval approach is also not something you see in most beginner projects. Pure recency-based memory breaks down in long conversations. Pure semantic memory misses recent context. Combining both gives you something that actually feels intelligent.

## Author

Built as part of a self-directed learning journey through AI engineering — from basic LangChain chains to production-grade memory systems.
