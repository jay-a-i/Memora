# backend/src/core/config.py

import json
from typing import List
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> parents[0]=core, parents[1]=src, parents[2]=backend
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """
    Configurations class for the whole project.
    """

    PROJECT_NAME: str        # MEMORA
    BACKEND_VERSION: str 
    CORS_ORIGINS: List[str]  

    # --- DATABASE ------------------------------------------------------------
    DATABASE_URL: str
    DB_ECHO: bool            # Log every statement in the terminal if True.
    DB_POOL_SIZE: int        
    DB_MAX_OVERFLOW: int

    # --- SECRETS ------------------------------------------------------------
    OPENROUTER_API_KEY: str  # Chat completions, via OpenRouter.
    COHERE_API_KEY: str      # Embeddings, via Cohere.
    TAVILY_API_KEY: str
    APP_API_KEY: str         # Key required to access resources from any api endpoint.

    # --- MODELS ------------------------------------------------------------
    LLM: str
    EMBEDDING_MODEL: str

    # --- EMBEDDING ------------------------------------------------------------
    EMBEDDING_DIMENSIONS: int
    EMBEDDING_BATCH_SIZE: int

    # --- Ingestion ------------------------------------------------------------
    UPLOAD_DIR: str
    MAX_UPLOAD_BYTES: int
    ALLOWED_EXTENSIONS: List[str]
    CHUNK_SIZE: int
    CHUNK_OVERLAP: int
    INGEST_BATCH_SIZE: int
    EXTRACT_IMAGES: bool

    # --- Agent ------------------------------------------------------------
    MAX_TOOL_CALLS: int
    MAX_LLM_CALLS: int
    MAX_HISTORY_MESSAGES: int

    #--- Tools --------------------------------------------------------------
    TOOL_CHOICE: str
    PARALLEL_TOOL_CALL: bool

    # --- LangGraph checkpointer --------------------------------------------
    CHECKPOINTER_POOL_SIZE: int
    CHECKPOINTER_TIMEOUT: float

    model_config = SettingsConfigDict(
        env_file= BACKEND_DIR / "app.env",
        extra="ignore",
    )


    @field_validator("DB_POOL_SIZE", "DB_MAX_OVERFLOW", "EMBEDDING_DIMENSIONS", "EMBEDDING_BATCH_SIZE",
                     "MAX_UPLOAD_BYTES", "CHUNK_SIZE", "CHUNK_OVERLAP", "INGEST_BATCH_SIZE", "MAX_TOOL_CALLS",
                     "MAX_LLM_CALLS", "MAX_HISTORY_MESSAGES", "CHECKPOINTER_POOL_SIZE", mode="before")
    @classmethod
    def str_to_int(cls, v: str) -> int:
        if type(v) == str:
            return int(v.strip())
        return v
    

    @field_validator("CHECKPOINTER_TIMEOUT", mode="before")
    @classmethod
    def str_to_float(cls, v: str) -> float:
        if type(v) == str:
            return float(v.strip())
        return v

    @field_validator("CORS_ORIGINS", "ALLOWED_EXTENSIONS", mode="before")
    @classmethod
    def _split_csv_to_valid_cors(cls, v):
        """Accept a JSON array, a comma-separated string, or a list."""
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v.startswith("["):
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
