# backend/app/tools/doc_inspector.py

import logging
import uuid

from sqlalchemy import text

from src.core.errors import client_message

logger = logging.getLogger(__name__)

MAX_WINDOW = 5  # Caps how much text one tool call can pull into the context.

DOC_INSPECTOR_SCHEMA = {
    "type": "function",
    "function": {
        "name": "doc_inspector",
        "description": (
            "Retrieves surrounding paragraphs (chunks) for a specific document. "
            "Use this tool when a previous search returns a relevant 'document_id' and 'chunk_index', "
            "but the 'content' seems cut off or you need more surrounding context to answer fully."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "string",
                    "description": "The UUID of the document (retrieved from hybrid_search)."
                },
                "chunk_index": {
                    "type": "integer",
                    "description": "The exact integer index of the chunk you want to inspect."
                },
                "window_size": {
                    "type": "integer",
                    "description": f"How many chunks before and after to retrieve. Default is 1, maximum is {MAX_WINDOW}.",
                    "default": 1
                }
            },
            "required": ["document_id", "chunk_index"],
        },
    },
}

INSPECT_SQL = text(
    """
    SELECT c.chunk_index, c.content, d.filename
    FROM document_chunks c
    JOIN documents d ON d.id = c.document_id
    WHERE c.document_id = CAST(:doc_id AS UUID)
      AND c.chunk_index >= :start_idx
      AND c.chunk_index <= :end_idx
    ORDER BY c.chunk_index ASC;
    """
)


async def execute_doc_inspector(
    document_id: str,
    chunk_index: int,
    window_size: int = 1,
    db_session=None,
    **kwargs
) -> list:
    if not db_session:
        return [{"error": "Database session missing. Cannot inspect document."}]

    # Validated before the query so a malformed UUID produces a usable message
    # for the model instead of a Postgres cast error.
    try:
        doc_uuid = uuid.UUID(str(document_id))
    except (ValueError, AttributeError, TypeError):
        return [{"error": f"'{document_id}' is not a valid document UUID."}]

    try:
        window_size = max(0, min(int(window_size), MAX_WINDOW))
        result = await db_session.execute(
            INSPECT_SQL,
            {
                "doc_id": str(doc_uuid),
                "start_idx": max(0, int(chunk_index) - window_size),
                "end_idx": int(chunk_index) + window_size,
            },
        )

        rows = result.mappings().all()

        if not rows:
            return [
                {
                    "warning": (
                        f"No chunks found for document {document_id} around "
                        f"index {chunk_index}."
                    )
                }
            ]

        return [
            {
                "source": row["filename"],
                "chunk_index": row["chunk_index"],
                "content": row["content"],
            }
            for row in rows
        ]

    except Exception as e:
        logger.exception("Document inspection failed")
        return [{"error": f"Document inspection failed: {client_message(e)}"}]