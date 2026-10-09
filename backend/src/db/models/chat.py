# backend/app/db/models/chat.py

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.src.db.models import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False, default="New Chat")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    messages = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        # `seq` is the authoritative order; created_at can tie on coarse clocks.
        order_by="ChatMessage.seq",
    )

    __table_args__ = (Index("idx_chat_sessions_updated", text("updated_at DESC")),)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role = Column(String(50), nullable=False)  # 'user', 'assistant', 'system', 'tool'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    # Monotonic insertion order, assigned by the database. Timestamps alone are
    # not enough: Windows clocks have ~15.6ms granularity, so a user message and
    # its assistant reply routinely share a created_at, and ordering by id
    # instead would sort random UUIDv4 values — correct only ~50% of the time.
    seq = Column(BigInteger, Identity(always=True), nullable=False, unique=True)

    session = relationship("ChatSession", back_populates="messages")

    __table_args__ = (Index("idx_chat_messages_session", "session_id", "seq"),)