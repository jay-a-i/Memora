import json
from typing import List, Annotated
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, NoDecode

#backend/core/config.py -> parents[0]=core, parents[1]=backend
BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """
    Configurations class for the whole project.
    """

    PROJECT_NAME: str        
    BACKEND_VERSION: str 
    CORS_ORIGINS: Annotated[list[str], NoDecode]

    #Database
    DATABASE_URL: str
    DB_ECHO: bool            
    DB_POOL_SIZE: int = Field(gt=0)
    DB_MAX_OVERFLOW: int = Field(ge=-1)

    #API KEYS
    OPENROUTER_API_KEY: str 
    COHERE_API_KEY: str     
    TAVILY_API_KEY: str
    APP_API_KEY: str        

    #Models
    LLM: str
    EMBEDDING_MODEL: str

    #Embeddings
    EMBEDDING_DIMENSIONS: int = Field(gt=0)
    EMBEDDING_BATCH_SIZE: int = Field(gt=0)

    #Ingestion
    MAX_UPLOAD_BYTES: int = Field(gt=0)
    CHUNK_SIZE: int = Field(gt=0)
    CHUNK_OVERLAP: int = Field(ge=0)
    INGEST_BATCH_SIZE: int = Field(gt=0)
    UPLOAD_DIR: str
    ALLOWED_EXTENSIONS: Annotated[list[str], NoDecode]
    EXTRACT_IMAGES: bool

    #Agent
    MAX_TOOL_CALLS: int = Field(gt=0)
    MAX_LLM_CALLS: int = Field(gt=0)
    MAX_CONTEXT_TOKENS: int = Field(gt=0)
    TOOL_CHOICE: str
    PARALLEL_TOOL_CALL: bool

    #Checkpointer
    CHECKPOINTER_POOL_SIZE: int = Field(gt=0)
    CHECKPOINTER_TIMEOUT: float = Field(gt=0)

    model_config = SettingsConfigDict(
        env_file= BACKEND_DIR / "app.env",
        extra="ignore",
    )


    @field_validator(
        "OPENROUTER_API_KEY",
        "COHERE_API_KEY",
        "APP_API_KEY",
        mode="before",
    )
    @classmethod
    def validate_required_keys(cls, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("This API key cannot be empty.")
        return value.strip()

    @field_validator("CORS_ORIGINS", "ALLOWED_EXTENSIONS", mode="before")
    @classmethod
    def parse_string_lists(cls, value):
        if isinstance(value, str):
            value = value.strip()

            if not value:
                return []

            if value.startswith("["):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError as e:
                    raise ValueError("Invalid JSON list.") from e
            else:
                value = value.split(",")

        if not isinstance(value, (list, tuple)):
            raise ValueError("Expected a list or comma-separated string.")

        if not all(isinstance(item, str) for item in value):
            raise ValueError("Every list item must be a string.")

        return [item.strip() for item in value if item.strip()]


    @field_validator("DATABASE_URL")
    @classmethod
    def _require_async_driver(cls, v: str) -> str:
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        return v


    @field_validator(
        "LLM", 
        "EMBEDDING_MODEL", 
        mode="after"
    )
    @classmethod
    def _reject_blank_model_id(cls, v: str) -> str:
        if not v.strip():
            raise ValueError(
                "Must put an LLM and Embedding model in app.env"
            )
        return v

    
    @model_validator(mode="after")
    def _check_chunk_overlap(self) -> "Settings":
        if self.CHUNK_OVERLAP >= self.CHUNK_SIZE:
            raise ValueError(
                f"CHUNK_OVERLAP ({self.CHUNK_OVERLAP}) must be less than "
                f"CHUNK_SIZE ({self.CHUNK_SIZE})"
            )
        return self

settings = Settings()
