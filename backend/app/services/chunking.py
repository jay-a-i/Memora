import logging
from typing import List, Optional

from langchain_core.documents import Document
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

HEADERS_TO_SPLIT_ON = [
    ("#", "Header 1"),
    ("##", "Header 2"),
    ("###", "Header 3"),
    ("####", "Header 4"),
    ("#####", "Header 5"),
    ("######", "Header 6"),
]


def chunk_text(file_path: str) -> Optional[List[Document]]:
    """Splits a Markdown file into semantic chunks based on headers and character count.

    Applies a two-stage chunking strategy: first splitting text at Markdown header boundaries
    (# through ######), followed by a recursive character split to enforce maximum token
    length constraints.

    Args:
        file_path (str): Path to the Markdown file to chunk.

    Returns:
        Optional[List[Document]]: A list of LangChain Document objects containing
        chunked text and header metadata if successful; otherwise None.

    Raises:
        OSError: If the file cannot be read.
    """
    # errors="replace" so a mis-encoded file degrades instead of failing. .txt is
    # an accepted upload format, and cp1252/latin-1 is what many Windows and
    # legacy tools emit; a strict read raised UnicodeDecodeError, which is not a
    # SafeError, so the document failed with a generic internal-error message
    # and could not be recovered without re-saving the file by hand.
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        md_text = f.read()

    if not md_text.strip():
        logger.warning("No text content in %s", file_path)
        return []

    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=HEADERS_TO_SPLIT_ON,
        strip_headers=False,
    )
    semantic_chunks = markdown_splitter.split_text(md_text)

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        separators=["\n\n", "\n", ".", " "],
    )

    final_chunks = text_splitter.split_documents(semantic_chunks)

    return [chunk for chunk in final_chunks if chunk.page_content.strip()]