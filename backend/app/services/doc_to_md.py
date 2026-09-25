import os, shutil
from typing import Dict
import pymupdf, pymupdf4llm

def doc_to_md(
    file_path: str, 
    output_md: str = "temp_output.md", 
    image_dir: str = "temp_image_dir", 
    batch_size: int = 50
) -> Dict[str, str] | None:
    
    """Converts a PDF file into Markdown format in memory-efficient page batches.

    Args:
        file_path (str): Path to the source PDF file.
        output_md (str, optional): Target file path for the output Markdown text. 
            Defaults to "temp_output.md".
        image_dir (str, optional): Directory path to extract embedded images into. 
            Defaults to "temp_image_dir".
        batch_size (int, optional): Number of PDF pages to process per batch to manage 
            RAM usage. Defaults to 50.

    Returns:
        Dict[str, str]: A dictionary containing file paths for 'output_md' and 'image_dir' if successful; otherwise None.
    """
    
    if os.path.exists(output_md):
        os.remove(output_md)
    if os.path.exists(image_dir):
        shutil.rmtree(image_dir)

    try:
        with pymupdf.open(file_path) as doc:
            total_pages = len(doc)
            
            with open(output_md, "a", encoding="utf-8") as f:
                for i in range(0, total_pages, batch_size):
                    end_page = min(i + batch_size, total_pages)
                    pages_to_extract = list(range(i, end_page))
                    
                    md_batch = pymupdf4llm.to_markdown(
                        doc, 
                        pages=pages_to_extract,
                        write_images=True, 
                        image_path=image_dir,
                        force_ocr=False
                    )
                    f.write(md_batch + "\n\n")
                    print(f"Processed pages {i} to {end_page - 1}")
                    
        return {
            "output_md": output_md,
            "image_dir": image_dir
        }
    
    except Exception as e:
        return None