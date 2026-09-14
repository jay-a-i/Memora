# backend/app/tools/doc_inspector.py

from sqlalchemy import text

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
                    "description": "How many chunks before and after to retrieve. Default is 1.",
                    "default": 1
                }
            },
            "required": ["document_id", "chunk_index"],
        },
    },
}

async def execute_doc_inspector(
    document_id: str, 
    chunk_index: int, 
    window_size: int = 1, 
    db_session=None, 
    **kwargs
) -> list:
    if not db_session:
        return [{"error": "Database session missing. Cannot inspect document."}]
        
    try:
        # SQL fetches chunks surrounding the target index
        sql = text("""
            SELECT chunk_index, content
            FROM document_chunks
            WHERE document_id = CAST(:doc_id AS UUID)
              AND chunk_index >= :start_idx
              AND chunk_index <= :end_idx
            ORDER BY chunk_index ASC;
        """)
        
        result = await db_session.execute(sql, {
            "doc_id": document_id,
            "start_idx": chunk_index - window_size,
            "end_idx": chunk_index + window_size
        })
        
        rows = result.mappings().all()
        
        if not rows:
            return [{"warning": f"No chunks found for document {document_id} around index {chunk_index}."}]
            
        return [
            {
                "chunk_index": row["chunk_index"],
                "content": row["content"]
            } 
            for row in rows
        ]
        
    except Exception as e:
        return [{"error": f"Document inspection failed: {str(e)}"}]