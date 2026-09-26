#backend/app/services/embedding.py

from typing import List, Optional
from backend.app.core.config import settings
from langchain_openai import OpenAIEmbeddings

Embedder = OpenAIEmbeddings(
        model="nvidia/llama-nemotron-embed-vl-1b-v2:free", 
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.OPENROUTER_API_KEY, 
        model_kwargs={"extra_body": {"truncate": "NONE"}},
        check_embedding_ctx_length=False
    )

async def generate_embeddings(
        texts: List[str], 
        batch_size: int = 32
    ) -> Optional[List[List[float]]]:

    """
    Asynchronously generates dense vector embeddings for a list of text strings in API batches.

    Args:
        texts (List[str]): List of raw text chunks to embed.
        batch_size (int, optional): Number of texts to send per API request. 
            Defaults to 32.

    Returns:
        Optional[List[List[float]]]: A list of floating-point vector arrays corresponding to each input text.
            Returns an empty list if `texts` is empty.

    Raises:
        RuntimeError: If the embedding API request fails.
    """
    if not texts:
        return []
    
    all_embeddings = []
    total_chunks = len(texts)

    for i in range(0, total_chunks, batch_size):
        batch = texts[i : i + batch_size]
        print(f"Embedding batch {i // batch_size + 1} / {(total_chunks + batch_size - 1) // batch_size}...")
        try:
            embeddings = await Embedder.aembed_documents(batch)
            all_embeddings.extend(embeddings)
        except Exception as e:
            return f"Error occured in Embedding Model\n[Error]: [{e}]"
            
    print("Successfully generated embeddings")
    print(f"Length of embeddings list: {len(all_embeddings)}")
    return all_embeddings
