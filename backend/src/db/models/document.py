#backend/app/db/models/document.py

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from src.db.models import Base
from src.core.config import settings


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)
    status = Column(
        String(50), nullable=False, default="PROCESSING"
    )  # 'PROCESSING', 'COMPLETED', 'FAILED'
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    chunks = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (Index("idx_documents_created", text("created_at DESC")),)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)
    embedding = Column(Vector(settings.EMBEDDING_DIMENSIONS))
    # GENERATED ALWAYS ... STORED mirrors schema.sql so the ORM and the DDL that
    # actually created the table agree; a plain column would stay NULL and
    # silently disable the keyword half of hybrid_search.
    fts_content = Column(
        TSVECTOR, Computed("to_tsvector('english', content)", persisted=True)
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    document = relationship("Document", back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunk_position"),
        Index("idx_chunks_document", "document_id"),
        Index("idx_chunks_fts", "fts_content", postgresql_using="gin"),
    )