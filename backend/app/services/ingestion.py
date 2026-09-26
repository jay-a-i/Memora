import os
import uuid
import shutil
from sqlalchemy import select

from backend.app.core.database import AsyncSessionLocal
from backend.app.db.models.document import Document, DocumentChunk
from backend.app.services.doc_to_md import doc_to_md
from backend.app.services.chunking import chunk_text
from backend.app.services.embedding import embed_documents
from backend.schemas import DocumentStatus

class ProcessFile:

    def __init__(self, doc_converter=doc_to_md, chunker=chunk_text, embedder=embed_documents):
        self.doc_to_md = doc_converter
        self.chunk_text = chunker
        self.embed_documents = embedder

    async def upload_file(
        self,
        file_path: str,
        db_batch_size: int = 500
    ) -> str:
        """Executes the full pipeline: conversion, chunking, embedding, and database ingestion.

        Args:
            file_path (str): Path to the target document.
                The filename is expected to follow the pattern "{document_id}_{original_filename}",
                matching the convention used by the upload endpoint when saving temporary files.
            db_batch_size (int, optional): Number of database records to bulk insert
                per transaction. Defaults to 500.

        Returns:
            str: Status message indicating whether the upload succeeded or failed.
        """
        document_id = None
        temp_files_to_clean = [file_path]

        try:
            filename = os.path.basename(file_path)
            prefix = filename.split("_", 1)[0]
            try:
                document_id = uuid.UUID(prefix)
            except ValueError:
                return "FAILED: Could not parse document ID from filename."

            async with AsyncSessionLocal() as db_session:
                stmt = select(Document).where(Document.id == document_id)
                result = await db_session.execute(stmt)
                doc = result.scalar_one_or_none()
                if not doc:
                    return f"FAILED: Document {document_id} not found in database."

                file_ext = os.path.splitext(file_path)[1].lower()

                if file_ext == ".pdf":
                    base_dir = os.path.dirname(file_path)
                    output_md = os.path.join(base_dir, f"{document_id}_converted.md")
                    image_dir = os.path.join(base_dir, f"{document_id}_images")
                    temp_files_to_clean.extend([output_md, image_dir])

                    conversion_result = self.doc_to_md(
                        file_path,
                        output_md=output_md,
                        image_dir=image_dir,
                    )
                    if conversion_result is None:
                        raise ValueError("PDF to Markdown conversion failed.")
                    md_path = conversion_result["output_md"]

                elif file_ext in (".txt", ".md"):
                    md_path = file_path

                else:
                    raise ValueError(f"Unsupported file format: {file_ext}")

                chunks = self.chunk_text(md_path)
                if not chunks:
                    raise ValueError("No content chunks produced from document.")

                chunk_contents = [chunk.page_content for chunk in chunks]
                embeddings = await self.embed_documents(chunk_contents)

                if isinstance(embeddings, str):
                    raise RuntimeError(f"Embedding generation failed: {embeddings}")
                if not embeddings or len(embeddings) != len(chunks):
                    raise RuntimeError(
                        f"Embedding count mismatch: {len(embeddings)} embeddings "
                        f"for {len(chunks)} chunks."
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
                    batch = chunk_records[i : i + db_batch_size]
                    db_session.add_all(batch)
                    await db_session.flush()

                doc.status = DocumentStatus.COMPLETED.value
                await db_session.commit()

                return (
                    f"SUCCESS: Document {document_id} processed successfully — "
                    f"{len(chunk_records)} chunks created and embedded."
                )

        except Exception as e:
            if document_id:
                try:
                    async with AsyncSessionLocal() as db_session:
                        stmt = select(Document).where(Document.id == document_id)
                        result = await db_session.execute(stmt)
                        doc = result.scalar_one_or_none()
                        if doc:
                            doc.status = DocumentStatus.FAILED.value
                            doc.error_message = str(e)
                            await db_session.commit()
                except Exception:
                    pass
            return f"FAILED: {str(e)}"

        finally:
            for path in temp_files_to_clean:
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path, ignore_errors=True)
                    elif os.path.exists(path):
                        os.remove(path)
                except Exception:
                    pass