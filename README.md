# 🛠️ Project Status: Under Reconstruction!
I'm currently restructuring the project's architecture and folder layout into the following format:

```text
├── frontend/  # Vibe Coding the frontend part
└── backend/
    ├── app/
    │   ├── api/
    │   │   └── v1/
    │   │       ├── endpoints/
    │   │       │   ├── chat.py              # SSE streaming endpoint for agentic RAG
    │   │       │   ├── documents.py         # Document upload & ingestion triggers
    │   │       │   └── health.py
    │   │       └── api.py                   # Router aggregation
    │   ├── core/
    │   │   ├── config.py                    # Pydantic BaseSettings (keys, DB URLs)
    │   │   ├── database.py                  # SQLAlchemy / SQLModel async engines
    │   │   └── security.py                  # API key validation / Auth
    │   ├── db/
    │   │   ├── models/                      # DB Schemas (Documents, Chunks, Messages)
    │   │   └── migrations/                  # Alembic migration scripts
    │   ├── agents/
    │   │   ├── orchestrator.py              # Core ReAct loop engine
    │   │   ├── prompts.py                   # System prompts and tool definitions
    │   │   └── state.py                     # Agent execution state dataclasses
    │   ├── tools/                           # Custom Python tools for the Agent
    │   │   ├── hybrid_search.py             # Vector + Keyword search on Postgres
    │   │   ├── doc_inspector.py             # Fetch surrounding chunks / full doc
    │   │   ├── metadata_filter.py           # SQL metadata query tool
    │   │   └── web_search.py                # External search fallback
    │   ├── services/
    │   │   ├── doc_to_md.py                 # Convert the Target file to a markdown file
    │   │   ├── chunking.py                  # Chunk the markdown file
    │   │   ├── embedding.py                 # Embedding generator wrappers
    │   │   └── ingestion.py                 # Background pipeline logic
    │   └── schemas/                         # Pydantic schemas for request/response
    ├── alembic/
    ├── Dockerfile
    ├── pyproject.toml                       # Dependencies for the entire backend
    └── main.py                              # Application entry point
```
