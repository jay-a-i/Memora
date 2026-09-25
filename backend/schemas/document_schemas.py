# backend/app/schemas/document_schemas.py

from datetime import datetime
from enum import Enum
from typing import List, Optional, Any, Dict
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class DocumentStatus(str, Enum):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class DocumentUploadResponse(BaseModel):
    document_id: UUID
    filename: str
    status: DocumentStatus = DocumentStatus.PROCESSING
    message: str = "File uploaded successfully. Processing started in background."


class DocumentChunkResponse(BaseModel):
    id: UUID
    content: str
    chunk_index: int
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class DocumentResponse(BaseModel):
    id: UUID
    filename: str
    file_type: str
    status: DocumentStatus
    error_message: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentListResponse(BaseModel):
    documents: List[DocumentResponse]
    total: int