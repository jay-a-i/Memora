from models import DocumentChunk
import os
from dotenv import load_dotenv
from typing import List
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings

load_dotenv()

def chunk_text(
    text: str, 
    chunk_size: int = 1000, 
    chunk_overlap: int = 150
) -> List[str]:
    """
    Splits document content into structured, overlapping string segments.
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""]
    )
    return text_splitter.split_text(text)

Embedding_Model = NVIDIAEmbeddings(
  model="nvidia/nv-embed-v1", 
  api_key=os.getenv("OPENROUTER_API_KEY"), 
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