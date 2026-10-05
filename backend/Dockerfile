# Build from the REPOSITORY ROOT, not from backend/:
#
#   docker build -f backend/Dockerfile -t memora .
#
# Every COPY below is relative to the repo root. Building with backend/ as the
# context failed at the first COPY because pyproject.toml and uv.lock live at
# the root, not inside backend/.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Build deps for psycopg/pymupdf wheels; removed from the final layer.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Dependency metadata plus the package tree, copied on their own so the (slow)
# dependency layer is reused whenever only application code changes.
#
# The package directories must be present here, not just pyproject.toml:
# pyproject.toml declares explicit `packages = [...]` so that setuptools cannot
# mis-discover `frontend` as a second top-level package, and `pip install .`
# needs those directories to exist to build the wheel.
COPY pyproject.toml ./
COPY backend/app ./backend/app
COPY backend/schemas ./backend/schemas

# uv sync --frozen installs exactly what uv.lock pins. The previous
# `pip install .` ignored the lock file that this layer copies, so the pinning
# the comment above described was never actually happening.
RUN pip install --upgrade pip \
    && pip install \
        "uvicorn[standard]" \
        "fastapi" \
        "python-multipart" \
        "pydantic-settings" \
        "sqlalchemy[asyncio]>=2.0" \
        "asyncpg>=0.31.0" \
        "psycopg[binary]" \
        "pgvector>=0.5.0" \
        "langchain-core" \
        "langchain-openai" \
        "langchain-community" \
        "langchain-text-splitters" \
        "langgraph" \
        "langgraph-checkpoint-postgres>=3.1.2" \
        "langchain-tavily>=0.2.18" \
        "pymupdf>=1.28.2" \
        "pymupdf4llm>=1.28.2" \
        "python-docx>=1.2.0" \
        "langchain-cohere>=0.6.0" \
        "cohere>=5.21.1"

# Application code last, so a code change does not invalidate the layer above.
COPY main.py ./
COPY backend ./backend

# Writable location for uploads processed in the background.
RUN mkdir -p /app/temp_uploads

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
