import re
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Path separators and traversal sequences are stripped rather than escaped, so
# a filename like "../../etc/passwd" cannot escape the upload directory.
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")

MAX_FILENAME_LEN = 200


def _safe_filename(filename: str) -> str:
    """
    Reduces a client-supplied filename to a harmless basename.

    The length cap is applied to the stem only. Truncating the whole name could
    cut off the extension, and ingestion re-derives the format from the stored
    name — so a long filename would be accepted by the endpoint and then fail
    ingestion with "Unsupported file format".
    """
    name = Path(filename or "upload").name  # drops any directory component
    name = _UNSAFE_CHARS.sub("_", name).lstrip(".") or "upload"

    if len(name) <= MAX_FILENAME_LEN:
        return name

    stem, ext = os.path.splitext(name)
    # Keep room for the dot plus a short extension such as ".markdown".
    if len(ext) > 16:
        ext = ""
    keep = MAX_FILENAME_LEN - len(ext)
    return f"{stem[:keep]}{ext}"


def _discard_partial_upload(file_path: str) -> None:
    """
    Removes a temp file left behind by a failed upload.

    The path is derived from the request, so it is inside the upload directory
    by construction; the unresolved case is when the write itself failed and
    left nothing, which is why the existence check comes first.
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except OSError:
        logger.warning("Could not remove partial upload %s", file_path, exc_info=True)


def clamp_page(limit: int, offset: int, maximum: int) -> tuple[int, int]:
    """
    Bounds a limit/offset pair.

    `limit` needs a lower bound as well as an upper one: `LIMIT -1` is a SQL
    error, so a negative limit would surface as a 500 rather than a 4xx.
    """
    return max(1, min(limit, maximum)), max(offset, 0)
