#backend/app/services/embedding.py

from typing import List
from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings
from app.core.config import settings

Embedding_Model = NVIDIAEmbeddings(
  model="nvidia/nv-embed-v1", 
  api_key=settings.OPENROUTER_API_KEY, 
  truncate="NONE", 
)

async def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Asynchronously generates vector representation arrays for a list of string chunks.
    """

    if not texts:
        return [] 
    try:
        return await Embedding_Model.aembed_documents(texts)
    except Exception as e:
        return f"There was a problem in Embedding Model\n[Error]: [{e}]"