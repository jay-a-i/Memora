# backend/app/db/models/__init__.py

from sqlalchemy.orm import declarative_base

Base = declarative_base()

from app.db.models.chat import ChatSession, ChatMessage
from app.db.models.document import Document, DocumentChunk

__all__ = ["Base", "ChatSession", "ChatMessage", "Document", "DocumentChunk"]