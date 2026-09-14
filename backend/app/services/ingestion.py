# backend/app/services/ingestion.py

import os
import uuid
from pypdf import PdfReader
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.db.models.document import Document, DocumentChunk
from app.schemas.document_schemas import DocumentStatus
from app.services.chunking import chunk_text
from app.services.embedding import generate_embeddings

def extract_text_from_file(file_path: str) -> str:
    """Extracts raw string text based on file format."""
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        reader = PdfReader(file_path)
        extracted_text = []
        for page in reader.pages:
            content = page.extract_text()
            if content:
                extracted_text.append(content)
        return "\n".join(extracted_text)

    elif ext in [".txt", ".md"]:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    else:
        raise ValueError(f"Unsupported file format extension: {ext}")


async def process_and_embed_document(file_path: str, document_id: uuid.UUID):
    """
    Background worker pipeline. Executes independently using a fresh AsyncSession.
    """
    async with AsyncSessionLocal() as db_session:
        try:
            # 1. Fetch target document record
            stmt = select(Document).where(Document.id == document_id)
            result = await db_session.execute(stmt)
            doc = result.scalar_one_or_none()
            if not doc:
                return

            # 2. Extract text from saved file
            raw_text = extract_text_from_file(file_path)
            if not raw_text.strip():
                raise ValueError("Extracted document content is empty.")

            # 3. Create text chunks
            chunks = chunk_text(raw_text)

            # 4. Generate embeddings for all chunks in batch
            vectors = await generate_embeddings(chunks)

            # 5. Build DocumentChunk ORM instances
            chunk_records = []
            for idx, (chunk_content, vector) in enumerate(zip(chunks, vectors)):
                chunk_records.append(
                    DocumentChunk(
                        document_id=document_id,
                        content=chunk_content,
                        chunk_index=idx,
                        metadata_={"source": doc.filename},
                        embedding=vector,
                    )
                )

            db_session.add_all(chunk_records)

            # 6. Update processing status
            doc.status = DocumentStatus.COMPLETED.value
            await db_session.commit()

        except Exception as e:
            await db_session.rollback()

            # Record failure reason on the document row
            stmt = select(Document).where(Document.id == document_id)
            result = await db_session.execute(stmt)
            doc = result.scalar_one_or_none()
            if doc:
                doc.status = DocumentStatus.FAILED.value
                doc.error_message = str(e)
                await db_session.commit()

        finally:
            # Delete temporary upload from server disk
            if os.path.exists(file_path):
                os.remove(file_path)