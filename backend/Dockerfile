FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /backend

COPY pyproject.toml uv.lock ./
RUN uv sync -update

COPY server.py /backend
COPY backend ./backend

RUN mkdir -p /app/temp_uploads

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]