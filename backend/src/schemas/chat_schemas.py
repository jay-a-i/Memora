from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ChatMessageInputSchema(BaseModel):
    role: MessageRole
    content: str = Field(max_length=20_000)


class ChatMessageSchema(BaseModel):
    role: MessageRole
    content: str
    turn_id: str

    model_config = ConfigDict(from_attributes=True)


class ChatRequestSchema(BaseModel):
    session_id: str
    messages: List[ChatMessageInputSchema] = Field(min_length=1)

    turn_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description=(
            "Stable ID for one logical user turn. "
            "Reuse it when retrying that turn."
        ),
    )


class ChatSessionCreateSchema(BaseModel):
    title: Optional[str] = "New Chat"


class ChatSessionResponseSchema(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatHistoryResponseSchema(BaseModel):
    session_id: UUID
    messages: List[ChatMessageSchema]