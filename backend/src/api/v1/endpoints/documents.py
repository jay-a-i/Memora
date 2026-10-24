#backend/src/api/v1/endpoints/documents.py

import logging
import os
import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.db.database import get_db
from src.core.security import verify_api_hitter
from src.db.models.document import Document, DocumentChunk
from src.schemas import (
    DocumentListResponse,
    DocumentResponse,
    DocumentStatus,
    DocumentUploadResponse,
)
from src.services.ingestion import ProcessFile
from src.helper import (
    _safe_filename, 
    _discard_partial_upload, 
    clamp_page,
)

logger = logging.getLogger(__name__)

router = APIRouter() 


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a document for ingestion",
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(verify_api_hitter),
):
    """
    Accepts a document upload, logs an initial record in PostgreSQL with status 'PROCESSING',
    saves the file temporarily, and offloads parsing, chunking, and vector embedding
    to an asynchronous background task.
    """
    file_ext = os.path.splitext(file.filename or "")[1].lower()
    if file_ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported format '{file_ext}'. Allowed formats: "
                f"{', '.join(settings.ALLOWED_EXTENSIONS)}"
            ),
        )

    # Read with a running total so an oversized upload is rejected as it
    # streams in, rather than after buffering the whole file into memory.
    contents = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        contents.extend(chunk)
        if len(contents) > settings.MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=(
                    f"File exceeds the {settings.MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit."
                ),
            )

    doc_id = uuid.uuid4()
    safe_name = _safe_filename(file.filename)
    temp_file_path = os.path.join(settings.UPLOAD_DIR, f"{doc_id}_{safe_name}")

    # The file is written before the row is created. Doing it the other way
    # round left a committed PROCESSING row with no file behind it whenever the
    # write failed, and nothing retries or reaps such a row — it reported
    # PROCESSING forever. A file with no row is harmless: the upload directory
    # is temporary and the background task removes what it is given.
    try:
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        with open(temp_file_path, "wb") as f:
            f.write(contents)
    except Exception as e:
        logger.exception("Failed to persist upload to disk")
        _discard_partial_upload(temp_file_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save file to disk.",
        ) from e

    new_doc = Document(
        id=doc_id,
        filename=safe_name,
        file_type=file_ext.replace(".", ""),
        status=DocumentStatus.PROCESSING.value,
    )
    db.add(new_doc)
    try:
        await db.commit()
    except Exception as e:
        # Without this the temp file survives a row that will never be created,
        # so the reverse ordering only moves the leak rather than removing it.
        logger.exception("Failed to record the uploaded document")
        _discard_partial_upload(temp_file_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not record the upload. Please try again.",
        ) from e

    processor = ProcessFile()
    # The document id is passed explicitly rather than re-parsed from the
    # on-disk filename, so a name that does not begin with a UUID cannot break
    # ingestion.
    background_tasks.add_task(
        processor.upload_file,
        file_path=temp_file_path,
        document_id=doc_id,
    )

    return DocumentUploadResponse(
        document_id=doc_id,
        filename=safe_name,
        status=DocumentStatus.PROCESSING,
        message="Document uploaded successfully. Background processing started.",
    )


@router.get(
    "/",
    response_model=DocumentListResponse,
    summary="List uploaded documents",
)
async def list_documents(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(verify_api_hitter),
):
    """
    Retrieves uploaded documents and their current processing status.
    """
    page_limit, page_offset = clamp_page(limit, offset, 100)
    stmt = (
        select(Document)
        .order_by(Document.created_at.desc())
        .limit(page_limit)
        .offset(page_offset)
    )
    result = await db.execute(stmt)
    documents = list(result.scalars().all())

    total = await db.scalar(select(func.count()).select_from(Document))

    return DocumentListResponse(
        documents=[DocumentResponse.model_validate(d) for d in documents],
        total=total or 0,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get a document's ingestion status",
)
async def get_document_status(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(verify_api_hitter),
):
    """
    Fetches status and metadata for a single document by its UUID.
    """
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found.",
        )

    return DocumentResponse.model_validate(document)


@router.get(
    "/{document_id}/chunks",
    summary="List a document's stored chunks",
)
async def list_document_chunks(
    document_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(verify_api_hitter),
):
    """
    Returns the ingested chunks for a document so ingestion output can be
    inspected without a separate database client.
    """
    page_limit, page_offset = clamp_page(limit, offset, 200)
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found.",
        )

    chunks = await db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
        .limit(page_limit)
        .offset(page_offset)
    )

    return {
        "document_id": str(document_id),
        "chunks": [
            {
                "chunk_index": c.chunk_index,
                "content": c.content,
                "metadata": c.metadata_,
            }
            for c in chunks.scalars().all()
        ],
    }


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document and its chunks",
)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(verify_api_hitter),
):
    """
    Deletes a document from PostgreSQL.
    The ON DELETE CASCADE relationship automatically deletes associated chunks in pgvector.
    """
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )

    # The relationship uses passive_deletes, so the ON DELETE CASCADE removes
    # the chunks in the database rather than loading every row into memory.
    await db.delete(document)
    await db.commit()
    return None