import json
from typing import List
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#backend/core/config.py -> parents[0]=core, parents[1]=backend
BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """
    Configurations class for the whole project.
    """

    PROJECT_NAME: str        
    BACKEND_VERSION: str 
    CORS_ORIGINS: List[str]  

    # --- DATABASE ------------------------------------------------------------
    DATABASE_URL: str
    DB_ECHO: bool            
    DB_POOL_SIZE: int        
    DB_MAX_OVERFLOW: int

    # --- SECRETS ------------------------------------------------------------
    OPENROUTER_API_KEY: str 
    COHERE_API_KEY: str     
    TAVILY_API_KEY: str
    APP_API_KEY: str        

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
    MAX_CONTEXT_TOKENS: int

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
                     "MAX_LLM_CALLS", "MAX_HISTORY_MESSAGES", "MAX_CONTEXT_TOKENS","CHECKPOINTER_POOL_SIZE", 
                     mode="before")
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
        if not self.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY is required for chat completions.")
        if not self.COHERE_API_KEY:
            raise ValueError("COHERE_API_KEY is required for embeddings.")
        return self


    @field_validator(
        "LLM", 
        "EMBEDDING_MODEL", 
        mode="after"
    )
    @classmethod
    def _reject_blank_model_id(cls, v: str) -> str:
        if not v.strip():
            raise ValueError(
                "must name a model; remove the line from app.env to use the "
                "default, or set it to a real model id"
            )
        return v
    

    @field_validator( 
        "CHUNK_SIZE", 
        "EMBEDDING_BATCH_SIZE",
        "INGEST_BATCH_SIZE", 
        "MAX_TOOL_CALLS", 
        "MAX_LLM_CALLS", 
        "MAX_CONTEXT_TOKENS"
    )
    @classmethod
    def _reject_non_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Value must be greater that zero.")
        return v


    @field_validator("CHUNK_OVERLAP")
    @classmethod
    def _reject_negative_overlap(cls, value: int) -> int:
        if value < 0:
            raise ValueError("CHUNK_OVERLAP cannot be negative.")
        return value

    @model_validator(mode="after")
    def _check_chunk_overlap(self) -> "Settings":
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
