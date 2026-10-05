# backend/app/core/config.py

import json
from pathlib import Path
from typing import List

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> parents[0]=core, [1]=app, [2]=backend
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """
    Configurations class for the whole project.
    """

    PROJECT_NAME: str = "MEMORA"
    BACKEND_VERSION: str = "1.0"
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    # --- DATABASE ------------------------------------------------------------
    DATABASE_URL: str
    # Logs every statement with bound parameters at INFO, which includes
    # ingested document text and full embedding vectors. Off unless asked for.
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10

    # --- SECRETS ------------------------------------------------------------
    OPENROUTER_API_KEY: str  # Chat completions, via OpenRouter.
    COHERE_API_KEY: str      # Embeddings, via Cohere.
    TAVILY_API_KEY: str | None = None
    APP_API_KEY: str  # Key required to access resources from any api endpoint.

    # --- MODEL ------------------------------------------------------------
    LLM: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    EMBEDDING_MODEL: str = "embed-v5.0-pro"

    # --- EMBEDDING ------------------------------------------------------------
    EMBEDDING_DIMENSIONS: int = 1536
    EMBEDDING_BATCH_SIZE: int = 32

    # --- Ingestion ------------------------------------------------------------
    UPLOAD_DIR: str = "temp_uploads"
    MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024
    ALLOWED_EXTENSIONS: List[str] = [".pdf", ".txt", ".md", ".docx"]
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    INGEST_BATCH_SIZE: int = 500
    EXTRACT_IMAGES: bool = False  # Extracted images are not ingested, so off by default.

    # --- Agent ------------------------------------------------------------
    MAX_TOOL_CALLS: int = 8
    MAX_LLM_CALLS: int = 12
    MAX_HISTORY_MESSAGES: int = 20

    # --- LangGraph checkpointer -------------------------------------------
    # The agent's own state (message history + tool calls) is checkpointed to
    # Postgres per conversation, keyed by the chat session UUID as thread_id.
    # Set to false to fall back to the previous stateless behaviour, where the
    # caller supplies history on every request.
    CHECKPOINT_ENABLED: bool = True
    CHECKPOINT_POOL_SIZE: int = 5
    CHECKPOINT_TIMEOUT: float = 30.0

    model_config = SettingsConfigDict(
        # Absolute: a bare "app.env" resolves against the process working
        # directory, so starting uvicorn from the repo root silently found no
        # file and every required key read as missing.
        env_file=BACKEND_DIR / "app.env",
        extra="ignore",
    )

    @field_validator("CORS_ORIGINS", "ALLOWED_EXTENSIONS", mode="before")
    @classmethod
    def _split_csv(cls, v):
        """Accept a JSON array, a comma-separated string, or a list."""
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v.startswith("["):
                # Parsed here rather than returned as a string, because a
                # str->list field will not coerce the JSON text on its own.
                try:
                    return json.loads(v)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON list: {v!r}") from e
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @field_validator("DATABASE_URL")
    @classmethod
    def _require_async_driver(cls, v: str) -> str:
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        return v

    @model_validator(mode="after")
    def _check_model_credentials(self) -> "Settings":
        """
        Both model providers are required: OpenRouter serves chat completions,
        Cohere serves embeddings.

        Without this the app imports and starts, then fails per request with a
        provider-side error instead of naming the missing key at boot.
        """
        if not self.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY is required for chat completions.")
        if not self.COHERE_API_KEY:
            raise ValueError("COHERE_API_KEY is required for embeddings.")
        return self

    @field_validator("LLM", "EMBEDDING_MODEL", mode="after")
    @classmethod
    def _reject_blank_model_id(cls, v: str) -> str:
        """
        Guards against an empty model id reaching a provider.

        An `app.env` line like `LLM=""` sets the variable to an empty string,
        which overrides the default rather than falling back to it. The request
        then fails at the provider with a message that does not mention
        configuration, so the cause is easy to miss. Failing at startup names it.
        """
        if not v.strip():
            raise ValueError(
                "must name a model; remove the line from app.env to use the "
                "default, or set it to a real model id"
            )
        return v

    @field_validator("CHUNK_OVERLAP", "CHUNK_SIZE", "EMBEDDING_BATCH_SIZE",
                     "INGEST_BATCH_SIZE", "MAX_TOOL_CALLS", "MAX_LLM_CALLS")
    @classmethod
    def _reject_non_positive(cls, v: int) -> int:
        """
        These feed `range()` steps and loop bounds directly.

        A negative INGEST_BATCH_SIZE makes `range(0, n, -1)` empty, so the
        pipeline commits COMPLETED with zero chunks and reports success. Zero
        chunk size is rejected by the splitter. Fail at startup instead of
        storing an empty index with no error anywhere.
        """
        if v <= 0:
            raise ValueError(f"must be a positive integer (got {v})")
        return v

    @model_validator(mode="after")
    def _check_chunk_overlap(self) -> "Settings":
        """
        Overlap must stay below chunk size.

        `overlap > chunk_size` raises inside the splitter during ingestion.
        `overlap == chunk_size` is worse: it raises nothing and produces
        near-duplicate chunks only, so a mid-sized document produced 9816
        chunks instead of 68 -- billed and stored at 144x for no new content.
        """
        if self.CHUNK_OVERLAP >= self.CHUNK_SIZE:
            raise ValueError(
                f"CHUNK_OVERLAP ({self.CHUNK_OVERLAP}) must be less than "
                f"CHUNK_SIZE ({self.CHUNK_SIZE})"
            )
        return self


"""
    Global Singleton.
"""
settings = Settings()
