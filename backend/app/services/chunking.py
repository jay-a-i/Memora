from langchain_text_splitters import (
    MarkdownHeaderTextSplitter, 
    RecursiveCharacterTextSplitter)
from typing import List, Optional
from langchain_core.documents import Document

def chunk_text(
        file_path: str
    ) -> Optional[List[Document]]:
    """Splits a Markdown file into semantic chunks based on headers and character count.

    Applies a two-stage chunking strategy: first splitting text at Markdown header boundaries
    (# through ######), followed by a recursive character split to enforce maximum token 
    length constraints.

    Args:
        file_path (str): Path to the Markdown file to chunk.

    Returns:
        Optional[List[Document]]: A list of LangChain Document objects containing 
        chunked text and header metadata if successful; otherwise None.
    """

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            md_text = f.read()
    except Exception as e: raise e

    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
        ("####", "Header 4"),
        ("#####", "Header 5"),
        ("######", "Header 6"),
    ]

    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        strip_headers=False
    )
    try:
        semantic_chunks = markdown_splitter.split_text(md_text)
    except Exception as e: raise e
    
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", ".", " "])
    
    try:
        final_chunks = text_splitter.split_documents(semantic_chunks)
    except Exception as e: raise e
    
    return [chunk for chunk in final_chunks if chunk.page_content.strip()]