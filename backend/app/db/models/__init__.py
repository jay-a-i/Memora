# backend/app/db/models/__init__.py

from sqlalchemy.orm import declarative_base

Base = declarative_base()

from .chat import ChatSession, ChatMessage
from .document import Document, DocumentChunk

__all__ = ["Base", "ChatSession", "ChatMessage", "Document", "DocumentChunk"]