# backend/app/tools/hybrid_search.py

import logging

from sqlalchemy import text

from backend.app.core.config import settings
from backend.app.core.errors import client_message
from backend.app.services.embedding import embed_query

logger = logging.getLogger(__name__)

TOP_K = 5
CANDIDATES = 20
RRF_K = 60 

HYBRID_SEARCH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "hybrid_search",
        "description": (
            "Searches the internal knowledge base for highly relevant document snippets. "
            "Use this tool FIRST when the user asks questions about uploaded documents, internal data, "
            "or context-specific information. It combines conceptual meaning (vector search) "
            "with exact keyword matching (full-text search)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to look for in the database."
                }
            },
            "required": ["query"],
        },
    },
}

HYBRID_SEARCH_SQL = text(
    f"""
    WITH vector_search AS (
        SELECT c.document_id,
               c.chunk_index,
               c.content,
               d.filename,
               row_number() OVER (ORDER BY c.embedding <=> :vector) AS rank
        FROM document_chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.embedding IS NOT NULL
        ORDER BY c.embedding <=> :vector
        LIMIT :candidates
    ),
    fts_search AS (
        SELECT c.document_id,
               c.chunk_index,
               c.content,
               d.filename,
               row_number() OVER (
                   ORDER BY ts_rank_cd(c.fts_content, websearch_to_tsquery('english', :query)) DESC
               ) AS rank
        FROM document_chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.fts_content @@ websearch_to_tsquery('english', :query)
        ORDER BY ts_rank_cd(c.fts_content, websearch_to_tsquery('english', :query)) DESC
        LIMIT :candidates
    )
    SELECT COALESCE(v.document_id, f.document_id) AS document_id,
           COALESCE(v.chunk_index, f.chunk_index) AS chunk_index,
           COALESCE(v.filename, f.filename)       AS source,
           COALESCE(v.content, f.content)         AS content,
           COALESCE(1.0 / ({RRF_K} + v.rank), 0.0)
             + COALESCE(1.0 / ({RRF_K} + f.rank), 0.0) AS rrf_score
    FROM vector_search v
    FULL OUTER JOIN fts_search f
        ON v.document_id = f.document_id AND v.chunk_index = f.chunk_index
    ORDER BY rrf_score DESC
    LIMIT :top_k;
    """
)


async def execute_hybrid_search(query: str, db_session=None, **kwargs) -> list:
    if not db_session:
        return [{"error": "Database session missing. Cannot perform search."}]

    if not query or not query.strip():
        return [{"error": "Search query was empty."}]

    try:
        query_vector = await embed_query(query)

        result = await db_session.execute(
            HYBRID_SEARCH_SQL,
            {
                "vector": str(query_vector),
                "query": query,
                "candidates": CANDIDATES,
                "top_k": TOP_K,
            },
        )

        rows = result.mappings().all()

        if not rows:
            return [
                {
                    "note": (
                        "No documents in the knowledge base matched this query. "
                        "Tell the user the knowledge base has no relevant "
                        "information rather than answering from memory."
                    )
                }
            ]

        return [
            {
                "source": row["source"],
                "document_id": str(row["document_id"]),
                "chunk_index": row["chunk_index"],
                "content": row["content"],
                "relevance_score": round(float(row["rrf_score"]), 4),
            }
            for row in rows
        ]

    except Exception as e:
        logger.exception("Hybrid search failed")
        return [{"error": f"Hybrid search failed: {client_message(e)}"}]