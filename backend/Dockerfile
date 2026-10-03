FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Build deps for psycopg/pymupdf wheels; removed from the final layer.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Dependency metadata is copied on its own so the (slow) dependency layer is
# reused whenever only application code changes.
COPY pyproject.toml uv.lock ./
RUN pip install --upgrade pip && pip install .

COPY main.py ./
COPY backend ./backend

# Writable location for uploads processed in the background.
RUN mkdir -p /app/temp_uploads

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
