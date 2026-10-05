import asyncio
import logging
import os
import shutil
import uuid

from sqlalchemy import delete, select

from backend.app.core.config import settings
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.errors import SafeError, client_message, log_and_client_message
from backend.app.db.models.document import Document, DocumentChunk
from backend.app.services.chunking import chunk_text
from backend.app.services.doc_to_md import doc_to_md, docx_to_md
from backend.app.services.embedding import embed_documents
from backend.schemas import DocumentStatus

logger = logging.getLogger(__name__)


class ProcessFile:

    def __init__(self, doc_converter=doc_to_md, chunker=chunk_text, embedder=embed_documents):
        self.doc_to_md = doc_converter
        self.chunk_text = chunker
        self.embed_documents = embedder

    async def upload_file(
        self,
        file_path: str,
        document_id: uuid.UUID | str | None = None,
        db_batch_size: int | None = None,
    ) -> str:
        """Executes the full pipeline: conversion, chunking, embedding, and database ingestion.

        Args:
            file_path (str): Path to the target document.
            document_id: The document's UUID. Passed by the upload endpoint. When
                omitted it is parsed from the leading UUID in the filename, which
                the endpoint writes as "{document_id}_{original_filename}".
            db_batch_size (int, optional): Number of database records to flush
                per batch. Defaults to INGEST_BATCH_SIZE.

        Returns:
            str: Status message indicating whether the upload succeeded or failed.
        """
        db_batch_size = db_batch_size or settings.INGEST_BATCH_SIZE
        temp_files_to_clean = [file_path]

        try:
            if document_id is None:
                prefix = os.path.basename(file_path).split("_", 1)[0]
                try:
                    document_id = uuid.UUID(prefix)
                except ValueError:
                    return "FAILED: Could not parse document ID from filename."

            document_id = uuid.UUID(str(document_id))
            file_ext = os.path.splitext(file_path)[1].lower()

            async with AsyncSessionLocal() as db_session:
                result = await db_session.execute(
                    select(Document).where(Document.id == document_id)
                )
                doc = result.scalar_one_or_none()
                if not doc:
                    return f"FAILED: Document {document_id} not found in database."

                if file_ext == ".pdf":
                    base_dir = os.path.dirname(file_path)
                    output_md = os.path.join(base_dir, f"{document_id}_converted.md")
                    image_dir = os.path.join(base_dir, f"{document_id}_images")
                    temp_files_to_clean.extend([output_md, image_dir])

                    # PDF conversion is CPU- and disk-bound; running it inline
                    # would stall the event loop for every other request.
                    conversion_result = await asyncio.to_thread(
                        self.doc_to_md,
                        file_path,
                        output_md=output_md,
                        image_dir=image_dir,
                        extract_images=settings.EXTRACT_IMAGES,
                    )
                    if conversion_result is None:
                        raise SafeError(
                            "This PDF could not be converted to text. It may be "
                            "encrypted, damaged, or contain no extractable text."
                        )
                    md_path = conversion_result["output_md"]

                elif file_ext == ".docx":
                    # A .docx is a ZIP archive; it must be parsed, not read as
                    # text, or the chunks would be compressed binary noise.
                    base_dir = os.path.dirname(file_path)
                    output_md = os.path.join(base_dir, f"{document_id}_converted.md")
                    temp_files_to_clean.append(output_md)

                    conversion_result = await asyncio.to_thread(
                        docx_to_md, file_path, output_md=output_md
                    )
                    if conversion_result is None:
                        raise SafeError(
                            "This Word document could not be converted to text. "
                            "It may be damaged or contain no extractable text."
                        )
                    md_path = conversion_result["output_md"]

                elif file_ext in (".txt", ".md"):
                    md_path = file_path

                else:
                    raise SafeError(f"Unsupported file format: {file_ext}")

                chunks = await asyncio.to_thread(self.chunk_text, md_path)
                if not chunks:
                    raise SafeError(
                        "No content chunks produced from document. The file may "
                        "be empty or contain no extractable text."
                    )

                chunk_contents = [chunk.page_content for chunk in chunks]
                embeddings = await self.embed_documents(chunk_contents)

                if not embeddings or len(embeddings) != len(chunks):
                    raise SafeError(
                        f"Embedding count mismatch: {len(embeddings)} embeddings "
                        f"for {len(chunks)} chunks."
                    )

                await db_session.execute(
                    delete(DocumentChunk).where(
                        DocumentChunk.document_id == document_id
                    )
                )

                chunk_records = []
                for idx, (chunk, vector) in enumerate(zip(chunks, embeddings)):
                    chunk_records.append(
                        DocumentChunk(
                            document_id=document_id,
                            content=chunk.page_content,
                            chunk_index=idx,
                            metadata_={
                                "source": doc.filename,
                                **chunk.metadata,
                            },
                            embedding=vector,
                        )
                    )

                for i in range(0, len(chunk_records), db_batch_size):
                    db_session.add_all(chunk_records[i : i + db_batch_size])
                    await db_session.flush()

                doc.status = DocumentStatus.COMPLETED.value
                doc.error_message = None
                await db_session.commit()

                logger.info(
                    "Ingested document %s: %s chunks", document_id, len(chunk_records)
                )
                return (
                    f"SUCCESS: Document {document_id} processed successfully — "
                    f"{len(chunk_records)} chunks created and embedded."
                )

        except Exception as e:
            # The stored message reaches API clients and the LLM through
            # DocumentResponse and metadata_filter, so only the safe summary is
            # persisted; the traceback stays in the log.
            message = log_and_client_message(e, "Ingestion failed")
            if document_id:
                await self._mark_failed(document_id, message)
            return f"FAILED: {message}"

        finally:
            for path in temp_files_to_clean:
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path, ignore_errors=True)
                    elif os.path.exists(path):
                        os.remove(path)
                except Exception:
                    logger.warning("Could not clean up %s", path, exc_info=True)

    @staticmethod
    async def _mark_failed(document_id: uuid.UUID, message: str) -> None:
        """Records the failure on the document row, best effort."""
        try:
            async with AsyncSessionLocal() as db_session:
                result = await db_session.execute(
                    select(Document).where(Document.id == document_id)
                )
                doc = result.scalar_one_or_none()
                if doc:
                    doc.status = DocumentStatus.FAILED.value
                    # Re-sanitized here so a caller that reaches this method by
                    # another route still cannot persist raw exception text.
                    doc.error_message = client_message(SafeError(message))[:2000]
                    await db_session.commit()
        except Exception:
            logger.exception("Could not mark document %s as failed", document_id)