# backend/app/services/embedding.py

import logging
from typing import List

import cohere

from backend.app.core.config import settings
from backend.app.core.errors import EmbeddingError

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = settings.EMBEDDING_MODEL

cohere_client = cohere.AsyncClientV2(api_key=settings.COHERE_API_KEY)


def _validate(vectors: List[List[float]], expected: int) -> None:
    """
    Fails loudly when a vector's width disagrees with the database column.

    Without this, a mismatch surfaces much later as an opaque pgvector
    "expected 1536 dimensions, not 2048" error during ingestion.
    """
    if not vectors:
        raise EmbeddingError("Embedding provider returned no vectors.")
    width = len(vectors[0])
    if width != expected:
        raise EmbeddingError(
            f"Embedding dimension mismatch: {EMBEDDING_MODEL} returned "
            f"{width}-dimension vectors but the database column is "
            f"vector({expected}). Set EMBEDDING_DIMENSIONS to {width} (and "
            f"update schema.sql) or pick a {expected}-dimension model."
        )


async def embed_documents(
    texts: List[str],
    batch_size: int | None = None,
) -> List[List[float]]:
    """
    Asynchronously generates dense vector embeddings for a list of text strings in API batches.

    Args:
        texts (List[str]): List of raw text chunks to embed.
        batch_size (int, optional): Number of texts to send per API request.
            Defaults to EMBEDDING_BATCH_SIZE (capped at 96 for Cohere API limits).

    Returns:
        List[List[float]]: A list of floating-point vector arrays corresponding to each input text.
            Returns an empty list if `texts` is empty.

    Raises:
        RuntimeError: If the embedding API request fails or returns vectors of
            the wrong width.
    """
    if not texts:
        return []

    # Cohere API strictly caps texts per batch at 96
    max_cohere_batch = 96
    configured_batch = batch_size or settings.EMBEDDING_BATCH_SIZE
    effective_batch_size = min(configured_batch, max_cohere_batch)

    total_chunks = len(texts)
    batches = (total_chunks + effective_batch_size - 1) // effective_batch_size

    all_embeddings: List[List[float]] = []
    for i in range(0, total_chunks, effective_batch_size):
        batch = texts[i : i + effective_batch_size]
        batch_num = (i // effective_batch_size) + 1
        logger.info("Embedding batch %s/%s", batch_num, batches)
        try:
            response = await cohere_client.embed(
                texts=batch,
                model=EMBEDDING_MODEL,
                input_type="search_document",
                embedding_types=["float"],
                output_dimension=settings.EMBEDDING_DIMENSIONS,
            )
            all_embeddings.extend(response.embeddings.float_)
        except Exception as e:
            raise EmbeddingError(
                f"Embedding request failed for batch {batch_num}/{batches} "
                f"using '{EMBEDDING_MODEL}': {e}"
            ) from e

    _validate(all_embeddings, settings.EMBEDDING_DIMENSIONS)
    return all_embeddings


async def embed_query(query: str) -> List[float]:
    """
    Asynchronously generates a dense vector embedding for the query text.

    Args:
        query (str): raw text to embed.

    Returns:
        List[float]: A single embedding vector.

    Raises:
        ValueError: If `query` is empty.
        RuntimeError: If the embedding API request fails or the returned vector
            has the wrong width.
    """
    if not query or not query.strip():
        raise ValueError("Cannot embed an empty query.")

    try:
        response = await cohere_client.embed(
            texts=[query],
            model=EMBEDDING_MODEL,
            input_type="search_query",
            embedding_types=["float"],
            output_dimension=settings.EMBEDDING_DIMENSIONS,
        )
        vector = response.embeddings.float_
    except Exception as e:
        raise EmbeddingError(
            f"Embedding request failed using '{EMBEDDING_MODEL}': {e}"
        ) from e

    _validate([vector], settings.EMBEDDING_DIMENSIONS)
    return vector