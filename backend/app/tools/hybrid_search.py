# backend/app/tools/hybrid_search.py

import os
from sqlalchemy import text
from langchain_openai import OpenAIEmbeddings

# Ensure you have OPENAI_API_KEY in your .env for the embeddings
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

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

async def execute_hybrid_search(query: str, db_session=None, **kwargs) -> list:
    if not db_session:
        return [{"error": "Database session missing. Cannot perform search."}]
    
    try:
        # 1. Generate the vector for the search query
        query_vector = await embeddings.aembed_query(query)
        
        # 2. Execute the RRF (Reciprocal Rank Fusion) raw SQL query
        sql = text("""
            WITH vector_search AS (
                SELECT document_id, chunk_index, content, 
                       RANK() OVER (ORDER BY embedding <=> :vector) as rank
                FROM document_chunks
                ORDER BY embedding <=> :vector
                LIMIT 20
            ),
            fts_search AS (
                SELECT document_id, chunk_index, content, 
                       RANK() OVER (ORDER BY ts_rank_cd(fts_content, websearch_to_tsquery('english', :query)) DESC) as rank
                FROM document_chunks
                WHERE fts_content @@ websearch_to_tsquery('english', :query)
                LIMIT 20
            )
            SELECT COALESCE(v.document_id, f.document_id) as document_id, 
                   COALESCE(v.chunk_index, f.chunk_index) as chunk_index,
                   COALESCE(v.content, f.content) as content,
                   COALESCE(1.0 / (60 + v.rank), 0.0) + COALESCE(1.0 / (60 + f.rank), 0.0) as rrf_score
            FROM vector_search v
            FULL OUTER JOIN fts_search f 
                ON v.document_id = f.document_id AND v.chunk_index = f.chunk_index
            ORDER BY rrf_score DESC
            LIMIT 5;
        """)
        
        # pgvector expects vectors as string representations: "[0.1, 0.2, ...]"
        result = await db_session.execute(sql, {
            "vector": str(query_vector), 
            "query": query
        })
        
        rows = result.mappings().all()
        
        # Return cleanly formatted dictionaries for the LLM
        return [
            {
                "document_id": str(row["document_id"]),
                "chunk_index": row["chunk_index"],
                "content": row["content"],
                "relevance_score": round(row["rrf_score"], 4)
            } 
            for row in rows
        ]
        
    except Exception as e:
        return [{"error": f"Hybrid search failed: {str(e)}"}]