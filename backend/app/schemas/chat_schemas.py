# backend/app/schemas/chat_schemas.py

from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ChatMessageSchema(BaseModel):
    role: MessageRole
    content: str

    model_config = ConfigDict(from_attributes=True)


class ChatRequestSchema(BaseModel):
    session_id: str = Field(..., description="Unique UUID or thread ID for the chat session")
    messages: List[ChatMessageSchema] = Field(..., min_length=1, description="List of messages in conversation")


class ChatSessionCreateSchema(BaseModel):
    title: Optional[str] = "New Chat"


class ChatSessionResponseSchema(BaseModel):
    id: UUID
    title: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatHistoryResponseSchema(BaseModel):
    session_id: UUID
    messages: List[ChatMessageSchema]