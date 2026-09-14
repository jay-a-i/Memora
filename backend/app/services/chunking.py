# backend/app/services/chunking.py

from typing import List
from langchain_text_splitters import RecursiveCharacterTextSplitter


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