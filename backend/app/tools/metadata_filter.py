# backend/app/tools/metadata_filter.py

import logging
import uuid

from sqlalchemy import text

logger = logging.getLogger(__name__)

MAX_RESULTS = 20
VALID_STATUSES = ("PROCESSING", "COMPLETED", "FAILED")

METADATA_FILTER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "metadata_filter",
        "description": (
            "Lists documents in the knowledge base with their ingestion status and chunk counts, "
            "optionally filtered by filename, file type, or status. Use this tool when the user asks "
            "what has been uploaded ('what documents do you have?', 'is my file processed?') or when "
            "you need document IDs to pass to doc_inspector."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filename_contains": {
                    "type": "string",
                    "description": "Case-insensitive substring to match against the filename. Omit for all files."
                },
                "file_type": {
                    "type": "string",
                    "description": "File extension without the dot, e.g. 'pdf'. Omit for all types."
                },
                "status": {
                    "type": "string",
                    "enum": ["PROCESSING", "COMPLETED", "FAILED"],
                    "description": "Ingestion status to filter on. Omit for all statuses."
                }
            },
            "required": [],
        },
    },
}

# Identifiers are bound as parameters, never interpolated, so a filename filter
# cannot alter the shape of the statement.
FILTER_SQL = text(
    """
    SELECT d.id::text        AS document_id,
           d.filename,
           d.file_type,
           d.status,
           d.error_message,
           count(c.id)       AS chunk_count
    FROM documents d
    LEFT JOIN document_chunks c ON c.document_id = d.id
    WHERE (:filename IS NULL OR d.filename ILIKE '%' || :filename || '%')
      AND (:file_type IS NULL OR d.file_type = :file_type)
      AND (:status IS NULL OR d.status = :status)
    GROUP BY d.id
    ORDER BY d.created_at DESC
    LIMIT :limit;
    """
)


async def execute_metadata_filter(
    filename_contains: str | None = None,
    file_type: str | None = None,
    status: str | None = None,
    db_session=None,
    **kwargs
) -> list:
    if not db_session:
        return [{"error": "Database session missing. Cannot query metadata."}]

    if status is not None and status not in VALID_STATUSES:
        return [{"error": f"'{status}' is not a valid status."}]

    try:
        result = await db_session.execute(
            FILTER_SQL,
            {
                "filename": filename_contains,
                "file_type": file_type.lstrip(".").lower() if file_type else None,
                "status": status,
                "limit": MAX_RESULTS,
            },
        )

        rows = result.mappings().all()
        if not rows:
            return [{"note": "No documents matched the given filters."}]

        documents = []
        for row in rows:
            try:
                uuid.UUID(row["document_id"])
            except (ValueError, TypeError):
                continue
            documents.append(
                {
                    "document_id": row["document_id"],
                    "filename": row["filename"],
                    "file_type": row["file_type"],
                    "status": row["status"],
                    "chunk_count": row["chunk_count"],
                    **(
                        {"error_message": row["error_message"]}
                        if row["status"] == "FAILED"
                        else {}
                    ),
                }
            )

        return documents or [{"note": "No documents matched the given filters."}]

    except Exception as e:
        logger.exception("Metadata filter failed")
        return [{"error": f"Metadata filter failed: {e}"}]
