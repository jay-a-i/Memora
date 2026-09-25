import os
import uuid
from fastapi import (
    APIRouter,
    Depends,
    File,
    UploadFile,
    BackgroundTasks,
    HTTPException,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.db.models.document import Document
from backend.schemas.document_schemas import (
    DocumentUploadResponse,
    DocumentResponse,
    DocumentListResponse,
    DocumentStatus,
)
from app.services.ingestion import ProcessFile

router = APIRouter()

TEMP_UPLOAD_DIR = "temp_uploads"

@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Accepts a document upload, logs an initial record in PostgreSQL with status 'PROCESSING',
    saves the file temporarily, and offloads parsing, chunking, and vector embedding
    to an asynchronous background task.
    """
  
    allowed_extensions = {".pdf", ".txt", ".md"}
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported format '{file_ext}'. Allowed formats: {', '.join(allowed_extensions)}",
        )

    doc_id = uuid.uuid4()

    new_doc = Document(
        id=doc_id,
        filename=file.filename,
        file_type=file_ext.replace(".", ""),
        status=DocumentStatus.PROCESSING.value,
    )
    db.add(new_doc)
    await db.commit()

    os.makedirs(TEMP_UPLOAD_DIR, exist_ok=True)
    temp_file_path = os.path.join(TEMP_UPLOAD_DIR, f"{doc_id}_{file.filename}")

    try:
        contents = await file.read()
        with open(temp_file_path, "wb") as f:
            f.write(contents)
    except Exception as e:
        # Rollback and mark document as FAILED if disk write fails
        new_doc.status = DocumentStatus.FAILED.value
        new_doc.error_message = f"Failed to save temporary file: {str(e)}"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not save file to disk: {str(e)}",
        )

    # 5. Dispatch non-blocking ingestion job to FastAPI BackgroundTasks
    processor = ProcessFile()
    background_tasks.add_task(
        processor.upload_file,
        file_path=temp_file_path,
    )

    return DocumentUploadResponse(
        document_id=doc_id,
        filename=file.filename,
        status=DocumentStatus.PROCESSING,
        message="Document uploaded successfully. Background processing started.",
    )

@router.get("/", response_model=DocumentListResponse)
async def list_documents(db: AsyncSession = Depends(get_db)):
    """
    Retrieves all uploaded documents and their current processing status.
    """
    stmt = select(Document).order_by(Document.created_at.desc())
    result = await db.execute(stmt)
    documents = result.scalars().all()

    return DocumentListResponse(
        documents=[DocumentResponse.model_validate(doc) for doc in documents],
        total=len(documents),
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document_status(
    document_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """
    Fetches status and metadata for a single document by its UUID.
    """
    stmt = select(Document).where(Document.id == document_id)
    result = await db.execute(stmt)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found.",
        )

    return DocumentResponse.model_validate(document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """
    Deletes a document from PostgreSQL. 
    The ON DELETE CASCADE relationship automatically deletes associated chunks in pgvector.
    """
    stmt = select(Document).where(Document.id == document_id)
    result = await db.execute(stmt)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found.",
        )

    await db.delete(document)
    await db.commit()
    return None