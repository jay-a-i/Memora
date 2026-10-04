# backend/app/services/embeddingV1.py

"""
Deprecated alias for `embeddingV2`.

The OpenRouter embedding implementation that used to live here was removed when
Cohere became the embedding provider: Cohere is the only one offering a model
that emits vectors at the width this project's `vector(1536)` column expects.

Nothing imports this module any more. It is kept only so that an old import
fails with a pointer instead of an opaque ImportError. Delete it once you are
sure no stale branch references it.
"""

from backend.app.services.embeddingV2 import (  # noqa: F401
    EMBEDDING_MODEL,
    embed_documents,
    embed_query,
)

__all__ = ["EMBEDDING_MODEL", "embed_documents", "embed_query"]