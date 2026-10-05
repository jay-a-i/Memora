"""
Shared test fixtures.

Environment variables are set before any application module is imported,
because `backend.app.core.config` builds its settings singleton at import time.
"""

import os

# A routable-looking host would let the engine attempt a real connection and
# stall the suite; port 1 refuses immediately instead.
os.environ["DATABASE_URL"] = "postgresql+asyncpg://u:p@127.0.0.1:1/test"
os.environ["OPENROUTER_API_KEY"] = "test-openrouter"
os.environ["COHERE_API_KEY"] = "test-cohere"
os.environ["APP_API_KEY"] = "test-secret"
# Tests must not depend on the developer's local app.env or a real database.
os.environ["DB_ECHO"] = "false"
# EMBEDDING_DIMENSIONS is deliberately NOT pinned here: the tests assert that
# schema.sql and the ORM agree with whatever the app defaults to, so pinning it
# would hide exactly the drift those tests exist to catch.
# LLM and EMBEDDING_MODEL are likewise unpinned, so the defaults are exercised.

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


class StubSession:
    """
    Minimal AsyncSession stand-in.

    Returns empty result sets so endpoints exercise their real code paths
    (validation, auth, serialization) without a live PostgreSQL instance.
    """

    def __init__(self):
        self.added = []
        self.committed = False
        self.executed = []

    class _Result:
        def scalars(self):
            return self

        def scalar_one_or_none(self):
            return None

        def scalar(self):
            return 0

        def all(self):
            return []

        def mappings(self):
            return self

    async def execute(self, *args, **kwargs):
        self.executed.append(args[0] if args else None)
        return self._Result()

    async def commit(self):
        self.committed = True

    async def rollback(self):
        pass

    async def flush(self):
        pass

    async def refresh(self, *a, **k):
        pass

    def add(self, obj):
        self.added.append(obj)

    def delete(self, obj):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def stub_session():
    return StubSession()


# ------------------------------------------------------------ ingestion stub

# Ingestion opens its own sessions via AsyncSessionLocal rather than the request
# dependency, so it needs stubbing separately. Without this, any test that lets
# ingestion reach the database tries a real connection to port 1 and waits for
# the OS to refuse it.

_document_row = None


def _make_document_row():
    global _document_row
    if _document_row is None:
        import uuid as _uuid

        from backend.app.db.models.document import Document

        _document_row = Document(
            id=_uuid.uuid4(), filename="doc.md", file_type="md", status="PROCESSING"
        )
    return _document_row


class _IngestResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _IngestSession:
    def __init__(self, row):
        self._row = row
        self.added = []
        self.deleted = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt, *args, **kwargs):
        return _IngestResult(self._row)

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def flush(self):
        pass

    def add_all(self, rows):
        self.added.extend(rows)

    def add(self, row):
        self.added.append(row)


@pytest.fixture(autouse=True)
def stub_ingestion_db(monkeypatch, request):
    """
    Points ingestion at a stub session that reports the document as present.

    Autouse so no test can reach a real database by way of the background
    pipeline. The factory hands back the *same* session each call, so a test can
    inspect what ingestion queued. A test that needs the row to be *missing*
    asks for `missing_document_row`.
    """
    import backend.app.services.ingestion as ingestion_module

    row = None if "missing_document_row" in request.fixturenames else _make_document_row()
    session = _IngestSession(row)
    monkeypatch.setattr(ingestion_module, "AsyncSessionLocal", lambda: session)
    return session


@pytest.fixture
def missing_document_row(stub_ingestion_db):
    """Marks the stubbed Document lookup as returning nothing."""
    stub_ingestion_db._row = None
    return stub_ingestion_db


@pytest.fixture(scope="session")
def client(tmp_path_factory):
    """A TestClient whose database and agent calls are stubbed out."""
    from backend.app.core.database import get_db
    import backend.app.api.v1.endpoints.health as health_endpoint
    from backend.app.core.config import settings

    async def healthy():
        return {"status": "healthy", "database": "connected"}

    health_endpoint.check_db_health = healthy

    # Uploads write to disk, so point the directory at a throwaway location
    # rather than the repo's real temp_uploads.
    settings.UPLOAD_DIR = str(tmp_path_factory.mktemp("uploads"))

    from main import app

    app.dependency_overrides[get_db] = StubSession

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
def auth():
    return {"APP_SECURITY_KEY": "test-secret"}