# backend/app/core/config.py

import json
from typing import List

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configurations class for the whole project.
    """

    PROJECT_NAME: str = "MEMORA"
    BACKEND_VERSION: str = "1.0"
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    DATABASE_URL: str
    DB_ECHO: bool = True  # Log every statement in the terminal if True.
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10

    OPENROUTER_API_KEY: str
    TAVILY_API_KEY: str | None = None
    APP_API_KEY: str  # Key required to access resources from any api endpoint.

    EMBEDDING_DIMENSIONS: int = 2048
    EMBEDDING_BATCH_SIZE: int = 32

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
    MAX_FILE_UPLOAD_BYTES: int = 5 * 1024 * 1024

    model_config = SettingsConfigDict(
        env_file="app.env",
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
    def _check_openrouter_key(self) -> "Settings":
        """
        OpenRouter serves both the chat and embeddings endpoints, so its key
        is the only model credential the app needs.
        """
        if not self.OPENROUTER_API_KEY:
            raise ValueError(
                "OPENROUTER_API_KEY is required: OpenRouter serves both the "
                "chat completions and the embeddings endpoint."
            )
        return self

    @property
    def embedding_api_key(self) -> str:
        return self.OPENROUTER_API_KEY


"""
    Global Singleton.
"""
settings = Settings()
