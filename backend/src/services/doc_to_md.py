import logging
import os
import shutil
import docx
from typing import Dict

import pymupdf
import pymupdf4llm

from src.core.config import settings

logger = logging.getLogger(__name__)


def doc_to_md(
    file_path: str,
    output_md: str = "temp_output.md",
    image_dir: str = "temp_image_dir",
    batch_size: int = 50,
    extract_images: bool | None = None,
) -> Dict[str, str] | None:
    """Converts a PDF file into Markdown format in memory-efficient page batches.

    Args:
        file_path (str): Path to the source PDF file.
        output_md (str, optional): Target file path for the output Markdown text.
        batch_size (int, optional): Number of PDF pages to process per batch to manage
            RAM usage. Defaults to 50.
        extract_images (bool, optional): Write embedded images to disk. Defaults to
            EXTRACT_IMAGES. Images are not ingested, so this is off by default;
            enabling it only fills disk with files that are deleted after upload.

    Returns:
        Dict[str, str]: A dictionary containing file paths for 'output_md' and 'image_dir' if successful; otherwise None.
    """
    if extract_images is None:
        extract_images = settings.EXTRACT_IMAGES

    if os.path.exists(output_md):
        os.remove(output_md)
    if os.path.exists(image_dir):
        shutil.rmtree(image_dir)

    try:
        with pymupdf.open(file_path) as doc:
            if doc.is_encrypted and not doc.authenticate(""):
                logger.error("PDF is encrypted and cannot be opened: %s", file_path)
                return None

            total_pages = len(doc)
            if total_pages == 0:
                logger.error("PDF has no pages: %s", file_path)
                return None

            with open(output_md, "w", encoding="utf-8") as f:
                for i in range(0, total_pages, batch_size):
                    end_page = min(i + batch_size, total_pages)
                    pages_to_extract = list(range(i, end_page))

                    md_batch = pymupdf4llm.to_markdown(
                        doc,
                        pages=pages_to_extract,
                        write_images=extract_images,
                        image_path=image_dir if extract_images else None,
                        force_ocr=False,
                    )
                    f.write(md_batch + "\n\n")
                    logger.info("Converted pages %s-%s", i, end_page - 1)

        return {
            "output_md": output_md,
            "image_dir": image_dir
        }

    except Exception:
        logger.exception("PDF to Markdown conversion failed for %s", file_path)
        return None


def docx_to_md(
    file_path: str,
    output_md: str = "temp_output.md",
) -> Dict[str, str] | None:
    """Converts a .docx file to Markdown, preserving headings and lists.

    A .docx is a ZIP archive, so reading it as text would embed compressed
    binary noise. This extracts the document body and maps Word's paragraph
    styles onto Markdown headings.

    Args:
        file_path (str): Path to the source .docx file.
        output_md (str, optional): Target path for the Markdown output.

    Returns:
        Dict[str, str] | None: {'output_md': path} on success, else None.
    """
    try:
        document = docx.Document(file_path)

        lines: list[str] = []
        for para in document.paragraphs:
            text = para.text.strip()
            if not text:
                lines.append("")
                continue

            style = (para.style.name or "").lower() if para.style else ""
            if style.startswith("heading"):
                level = style.replace("heading", "").strip()
                if level.isdigit() and 1 <= int(level) <= 6:
                    lines.append(f"{'#' * int(level)} {text}")
                    continue

            lines.append(text)

        for table in document.tables:
            rows = [
                [cell.text.strip() for cell in row.cells] for row in table.rows
            ]
            if not rows:
                continue
            lines.append("")
            lines.append("| " + " | ".join(rows[0]) + " |")
            lines.append("| " + " | ".join("---" for _ in rows[0]) + " |")
            for row in rows[1:]:
                lines.append("| " + " | ".join(row) + " |")
            lines.append("")

        markdown = "\n\n".join(
            "\n".join(lines).split("\n\n\n")
        ).strip()

        if not markdown:
            logger.error("No extractable text in %s", file_path)
            return None

        with open(output_md, "w", encoding="utf-8") as f:
            f.write(markdown + "\n")

        return {"output_md": output_md}

    except Exception:
        logger.exception("DOCX to Markdown conversion failed for %s", file_path)
        return None
