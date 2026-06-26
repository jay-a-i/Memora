# Memora

A Retrieval-Augmented Generation (RAG) assistant with hybrid conversational memory.

Memora combines document retrieval and long-running chat memory to create an AI assistant that can answer questions from uploaded PDFs while maintaining context across conversations.

[Visit Live Website](https://memora-j.streamlit.app/)
---

## Features

### Retrieval-Augmented Generation (RAG)

Upload PDFs and chat with them.

Memora:

* extracts text from PDFs
* chunks documents using recursive text splitting
* generates embeddings with NVIDIA nv-embed-v1
* stores chunks in PostgreSQL + pgvector
* retrieves semantically relevant passages
* injects retrieved context into the prompt

If information is not found inside the retrieved context, the assistant avoids hallucinating and states that it could not find the answer.

---

### Hybrid Memory

Memora uses two memory layers:

#### Recent Memory

Maintains the latest conversation context by retrieving the most recent messages.

#### Semantic Memory

Searches past conversations using vector similarity to find relevant memories based on meaning rather than recency.

Both are merged and deduplicated before being sent to the model.

---

### Multi-Session Chats

Users can:

* create multiple conversations
* switch between chats
* reload previous sessions
* preserve chat history

---

### Document Library

Documents can be:

* uploaded
* listed
* deleted

Uploaded PDFs are automatically processed and indexed.

---

## Architecture

```text
User
 ↓
Streamlit UI
 ↓
FastAPI
 ↓
Hybrid Retrieval
 ├── Conversation Memory
 └── Document Retrieval
 ↓
OpenRouter LLM
 ↓
Streaming Response
```

---


## Tech stack

- **FastAPI** — async REST backend with streaming support
- **Streamlit** — frontend chat interface
- **LangChain** — LLM orchestration
- **PostgreSQL + pgvector** — persistent storage and vector similarity search
- **NVIDIA nv-embed-v1** — text embeddings (4096 dimensions)
- **OpenRouter** — LLM API access
- **psycopg3 + connection pooling** — efficient database connections
- **Neon** — hosted PostgreSQL with pgvector
- **Render** — backend deployment
- **Streamlit Cloud** — frontend deployment

---

## Retrieval Pipeline

### Conversation Memory

```
User Query
↓
Embedding
↓
Recent Messages
+
Semantic Memory Search
↓
Context Assembly
```

### Document Retrieval

```
PDF
↓
Chunking
↓
Embedding
↓
pgvector
↓
Similarity Search
↓
Relevant Chunks
↓
Prompt Injection
```

---

## Database Structure

### users

Stores user identities.

### sessions

Stores chat sessions.

### messages

Stores conversation history and message embeddings.

### documents

Stores uploaded PDFs.

### document_chunks

Stores chunked document contents and embeddings.

## Database schema

Five tables — users, sessions, messages, documents, and document_chunks. Messages and document chunks both store 4096-dimensional embedding vectors, which allows unified semantic search across conversation history and uploaded documents.

```sql
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

CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    filename TEXT NOT NULL,
    uploaded_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE document_chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id),
    content TEXT NOT NULL,
    embedding vector(4096),
    page_number INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

```

---

## Running Locally

### Install dependencies

```bash
git clone https://github.com/jay-a-i/Memora.git
cd Memora
pip install -r requirements.txt
```

### Environment variables

```env
OPENROUTER_API_KEY= Your Openrouter api key
NVIDIA_API_KEY= Your Nvidia api key
CBDB_URL= Your SQL database Url (or neon)
```

### Run backend

```bash
uvicorn main:app --reload
```

### Run frontend

```bash
streamlit run app.py
```

---

## Future Improvements

* automatic session titles
* long-term memory profiles
* conversation summaries
* Redis caching
* authentication
* Docker deployment
* LangGraph agents

---

## Motivation

Most tutorial chatbots only remember the last few messages.

Memora goes further by combining:

* hybrid conversational memory
* semantic retrieval
* persistent storage
* document-based RAG

to provide an assistant that can reason over both previous conversations and external knowledge.
