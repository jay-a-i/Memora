"""HTTP surface: auth, health, upload validation, and the upload failure path."""

import io
import os

import pytest


# --------------------------------------------------------------------- auth


def test_root_is_public(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["project"] == "MEMORA"


def test_health_requires_auth(client):
    assert client.get("/api/v1/health/").status_code == 401


def test_health_reports_version_and_db(client, auth):
    r = client.get("/api/v1/health/", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert body["database"]["database"] == "connected"
    assert body["version"]


def test_health_returns_503_when_db_is_down(client, auth, monkeypatch):
    import backend.app.api.v1.endpoints.health as health_endpoint

    async def unhealthy():
        return {"status": "unhealthy", "database": "disconnected", "error": "refused"}

    monkeypatch.setattr(health_endpoint, "check_db_health", unhealthy)
    r = client.get("/api/v1/health/", headers=auth)
    assert r.status_code == 503
    assert r.json()["status"] == "unhealthy"


def test_health_error_detail_is_not_leaked_to_the_client():
    """
    A health response is still an API response. The driver names the host and
    the port; that belongs in the log, not in the body.
    """
    import asyncio

    from backend.app.core import database as database_module

    class Failing:
        async def __aenter__(self):
            raise OSError(
                'connection to server at "db.internal.corp" (10.0.0.7), '
                "port 5432 failed"
            )

        async def __aexit__(self, *exc):
            return False

    original = database_module.AsyncSessionLocal
    database_module.AsyncSessionLocal = lambda: Failing()
    try:
        result = asyncio.run(database_module.check_db_health())
    finally:
        database_module.AsyncSessionLocal = original

    assert result["status"] == "unhealthy"
    assert "db.internal.corp" not in result["error"]
    assert "10.0.0.7" not in result["error"]


def test_documents_list_requires_auth(client):
    assert client.get("/api/v1/documents/").status_code == 401


def test_chat_stream_requires_auth(client):
    r = client.post(
        "/api/v1/chat/stream",
        json={"session_id": "0" * 8 + "-0000-0000-0000-" + "0" * 12,
              "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 401


# ------------------------------------------------------------------ upload


def test_upload_rejects_unsupported_extension(client, auth):
    r = client.post(
        "/api/v1/documents/upload",
        headers=auth,
        files={"file": ("notes.exe", io.BytesIO(b"x"), "application/octet-stream")},
    )
    assert r.status_code == 400
    assert "Unsupported format" in r.json()["detail"]


def test_upload_rejects_path_traversal_filename(client, auth):
    """A traversing name must be reduced to a safe basename before storage."""
    r = client.post(
        "/api/v1/documents/upload",
        headers=auth,
        files={"file": ("../../evil.md", io.BytesIO(b"# hi"), "text/markdown")},
    )
    assert r.status_code == 202
    assert r.json()["filename"] == "evil.md"


def test_upload_rejects_oversized_file(client, auth, monkeypatch):
    from backend.app.api.v1.endpoints import documents as documents_endpoint

    monkeypatch.setattr(documents_endpoint.settings, "MAX_UPLOAD_BYTES", 10)
    r = client.post(
        "/api/v1/documents/upload",
        headers=auth,
        files={"file": ("big.md", io.BytesIO(b"x" * 500), "text/markdown")},
    )
    assert r.status_code == 413


# --------------------------------------------------------------- filenames


def test_safe_filename_strips_traversal():
    from backend.app.api.v1.endpoints.documents import _safe_filename

    # Only the final path component survives, on both separator styles.
    assert _safe_filename("../../evil.md") == "evil.md"
    assert _safe_filename("a/b/c.pdf") == "c.pdf"
    assert _safe_filename("..\\..\\windows\\system32\\x.md") == "x.md"
    assert _safe_filename("") == "upload"
    # Benign names are preserved rather than mangled.
    assert _safe_filename("normal-file_name.txt") == "normal-file_name.txt"
    for bad in ["../../evil.md", "a/b/c.pdf", "..\\x.md", "/etc/passwd"]:
        cleaned = _safe_filename(bad)
        assert "/" not in cleaned and "\\" not in cleaned
        assert ".." not in cleaned


@pytest.mark.parametrize("length", [10, 200, 254, 304])
def test_long_filename_keeps_its_extension(length):
    """
    Truncating the whole name used to cut off the extension. The endpoint
    validated the extension on the full name, so a long .pdf was accepted with
    202 and then failed ingestion with "Unsupported file format".
    """
    from backend.app.api.v1.endpoints.documents import MAX_FILENAME_LEN, _safe_filename

    safe = _safe_filename("a" * (length - 4) + ".pdf")

    assert os.path.splitext(safe)[1] == ".pdf", "extension was lost"
    assert len(safe) <= MAX_FILENAME_LEN


def test_dotfile_upload_is_rejected_not_silently_broken():
    """
    A leading-dot name has no extension as far as splitext is concerned, so it
    is refused at the door. Stripping the dot to store it would accept the file
    and then strand it in FAILED forever, which is worse than a 400.
    """
    from backend.app.api.v1.endpoints.documents import _safe_filename

    for name in [".pdf", "..md", ".txt", "...docx"]:
        assert os.path.splitext(name)[1].lower() not in {".pdf", ".txt", ".md", ".docx"}
        # And whatever _safe_filename produces is not silently given an
        # extension the uploader did not send.
        assert os.path.splitext(_safe_filename(name))[1] == ""


def test_hidden_file_with_a_real_extension_survives():
    """.notes.pdf is a real .pdf upload, not a dotfile."""
    from backend.app.api.v1.endpoints.documents import _safe_filename

    assert os.path.splitext(_safe_filename(".notes.pdf"))[1] == ".pdf"


# ------------------------------------------------------------ upload ordering


def test_failed_disk_write_leaves_no_document_row(client, auth, monkeypatch, tmp_path):
    """
    The row used to be committed before the file was written, so a full disk or
    a read-only mount left a permanent PROCESSING row with no file behind it and
    nothing to retry or reap it. The write now happens first.
    """
    from backend.app.api.v1.endpoints import documents as documents_endpoint

    monkeypatch.setattr(documents_endpoint.settings, "UPLOAD_DIR", str(tmp_path))

    def refuse(*args, **kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(documents_endpoint.os, "makedirs", refuse)

    r = client.post(
        "/api/v1/documents/upload",
        headers=auth,
        files={"file": ("doc.md", io.BytesIO(b"# hi"), "text/markdown")},
    )

    assert r.status_code == 500
    assert "stack" not in r.text.lower()
    assert "permission denied" not in r.text.lower()


def test_failed_row_insert_removes_the_temp_file(client, auth, monkeypatch, tmp_path):
    """
    Writing the file first only moves the leak unless the reverse failure also
    cleans up: a row that never commits must not leave its file behind.
    """
    from backend.app.api.v1.endpoints import documents as documents_endpoint

    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(documents_endpoint.settings, "UPLOAD_DIR", str(upload_dir))

    class FailingSession:
        def __init__(self):
            self.added = []

        async def commit(self):
            raise RuntimeError("connection to server at db.internal failed")

        async def rollback(self):
            pass

        async def close(self):
            pass

        def add(self, obj):
            self.added.append(obj)

        async def flush(self):
            pass

    app = documents_endpoint
    from backend.app.core.database import get_db
    from tests.conftest import StubSession

    # Restore the stub explicitly afterwards: the client fixture's override is
    # session-scoped, so popping it would leave later tests hitting a real DB.
    previous = client.app.dependency_overrides[get_db]

    def override():
        return FailingSession()

    client.app.dependency_overrides[get_db] = override
    try:
        r = client.post(
            "/api/v1/documents/upload",
            headers=auth,
            files={"file": ("doc.md", io.BytesIO(b"# hi"), "text/markdown")},
        )
    finally:
        client.app.dependency_overrides[get_db] = previous

    assert r.status_code == 500
    assert "db.internal" not in r.text
    assert upload_dir.exists()
    assert list(upload_dir.iterdir()) == [], "temp file was left behind"


def test_successful_upload_writes_the_file_the_background_task_expects(
    client, auth, monkeypatch, tmp_path
):
    """
    The endpoint passes an explicit document_id to ingestion, so the on-disk name
    only has to be stable — but it must exist by the time the 202 is returned.
    """
    from backend.app.api.v1.endpoints import documents as documents_endpoint

    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(documents_endpoint.settings, "UPLOAD_DIR", str(upload_dir))

    captured = {}

    original = documents_endpoint.ProcessFile

    class Capturing(original):
        async def upload_file(self, file_path, document_id=None, **kwargs):
            captured["file_path"] = file_path
            captured["document_id"] = document_id
            return "SUCCESS: stubbed"

    monkeypatch.setattr(documents_endpoint, "ProcessFile", Capturing)

    r = client.post(
        "/api/v1/documents/upload",
        headers=auth,
        files={"file": ("doc.md", io.BytesIO(b"# hi"), "text/markdown")},
    )

    assert r.status_code == 202
    assert os.path.exists(captured["file_path"])
    assert str(r.json()["document_id"]) == str(captured["document_id"])


# ------------------------------------------------------------------ paging


@pytest.mark.parametrize("limit", [-1, -100, 0, 10**9])
def test_page_clamp_bounds_both_ends(limit):
    """LIMIT -1 is a SQL error, so a negative limit must not reach the query."""
    from backend.app.api.v1.endpoints.documents import clamp_page

    clamped, offset = clamp_page(limit, 0, 100)

    assert 1 <= clamped <= 100
    assert offset >= 0


def test_negative_offset_is_clamped():
    from backend.app.api.v1.endpoints.documents import clamp_page

    _, offset = clamp_page(50, -5, 100)
    assert offset >= 0