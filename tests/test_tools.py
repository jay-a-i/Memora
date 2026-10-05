"""Retrieval tool behaviour that does not need a live database."""

import asyncio
import uuid

import backend.app.tools.hybrid_search as hs
from backend.app.tools import TOOLS_MAP, tool_schemas
from backend.app.tools.doc_inspector import MAX_WINDOW, execute_doc_inspector
from backend.app.tools.hybrid_search import execute_hybrid_search
from backend.app.tools.metadata_filter import execute_metadata_filter
from backend.app.tools.web_search import execute_web_search


def run(coro):
    return asyncio.run(coro)


# ----------------------------------------------------------------- registry


def test_every_schema_name_has_an_executor():
    # A schema the model can call but the graph cannot run is a dead tool.
    names = {s["function"]["name"] for s in tool_schemas}
    assert names == set(TOOLS_MAP)


def test_schemas_are_well_formed():
    for schema in tool_schemas:
        fn = schema["function"]
        assert schema["type"] == "function"
        assert fn["parameters"]["type"] == "object"
        assert fn["description"]


def test_no_tool_exposes_a_database_handle_to_the_model():
    """
    db_session is injected by the orchestrator, never declared in a schema.
    A schema naming it would invite the model to pass one.
    """
    for schema in tool_schemas:
        assert "db_session" not in schema["function"]["parameters"].get(
            "properties", {}
        )


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.params = None
        self.sql = None

    async def execute(self, stmt, params=None):
        self.sql = str(stmt)
        self.params = params
        return _FakeResult(self.rows)


def _stub_embedding(monkeypatch):
    async def fake_embed(query):
        return [0.0] * 1536

    monkeypatch.setattr(hs, "embed_query", fake_embed)


# ------------------------------------------------------------ hybrid search


def test_hybrid_search_returns_source_filename(monkeypatch):
    """The prompt requires [Source X] citations, so results need a title."""
    _stub_embedding(monkeypatch)
    doc_id = str(uuid.uuid4())
    session = _FakeSession(
        [
            {
                "document_id": doc_id,
                "chunk_index": 0,
                "source": "handbook.pdf",
                "content": "text",
                "rrf_score": 0.03,
            }
        ]
    )

    result = run(execute_hybrid_search("vacation policy", db_session=session))
    assert result[0]["source"] == "handbook.pdf"
    assert result[0]["relevance_score"] == 0.03


def test_hybrid_search_sql_joins_documents_for_filename():
    # Without this join the model can only ever cite a bare UUID.
    assert "documents" in hs.HYBRID_SEARCH_SQL.text
    assert "filename" in hs.HYBRID_SEARCH_SQL.text


def test_hybrid_search_binds_the_vector_as_a_parameter(monkeypatch):
    """Interpolating a 1536-float vector into SQL text would be unusable."""
    _stub_embedding(monkeypatch)
    session = _FakeSession([])

    run(execute_hybrid_search("q", db_session=session))

    assert "<=>" in session.sql
    assert "0.0, 0.0" not in session.sql


def test_hybrid_search_handles_empty_result(monkeypatch):
    _stub_embedding(monkeypatch)
    result = run(execute_hybrid_search("nothing here", db_session=_FakeSession([])))
    assert "note" in result[0]


def test_hybrid_search_requires_session():
    result = run(execute_hybrid_search("q", db_session=None))
    assert "error" in result[0]


def test_hybrid_search_rejects_empty_query(monkeypatch):
    _stub_embedding(monkeypatch)
    result = run(execute_hybrid_search("   ", db_session=_FakeSession([])))
    assert "empty" in result[0]["error"].lower()


def test_hybrid_search_failure_does_not_leak_the_dsn(monkeypatch):
    """
    The error goes back to the model as a tool result, and the model can repeat
    it to the user. A driver message names the host and the credentials.
    """
    _stub_embedding(monkeypatch)

    class Failing(_FakeSession):
        async def execute(self, stmt, params=None):
            raise RuntimeError(
                'connection to server at "db.internal.corp" (10.0.0.7), '
                "port 5432 failed"
            )

    result = run(execute_hybrid_search("q", db_session=Failing()))

    assert "db.internal.corp" not in result[0]["error"]
    assert "10.0.0.7" not in result[0]["error"]


# ------------------------------------------------------------ doc inspector


def test_doc_inspector_rejects_malformed_uuid():
    result = run(execute_doc_inspector("not-a-uuid", 0, db_session=_FakeSession([])))
    assert "not a valid" in result[0]["error"].lower()


def test_doc_inspector_clamps_window():
    seen = {}

    class S(_FakeSession):
        async def execute(self, stmt, params=None):
            seen.update(params)
            return _FakeResult([])

    run(execute_doc_inspector(str(uuid.uuid4()), 10, 999, db_session=S()))
    assert seen["end_idx"] - seen["start_idx"] <= 2 * MAX_WINDOW


def test_doc_inspector_window_cannot_go_negative():
    seen = {}

    class S(_FakeSession):
        async def execute(self, stmt, params=None):
            seen.update(params)
            return _FakeResult([])

    run(execute_doc_inspector(str(uuid.uuid4()), 0, 5, db_session=S()))
    assert seen["start_idx"] >= 0


def test_doc_inspector_handles_a_missing_document():
    result = run(execute_doc_inspector(str(uuid.uuid4()), 0, db_session=_FakeSession([])))
    assert "warning" in result[0]


# ---------------------------------------------------------- metadata filter


def test_metadata_filter_rejects_bad_status():
    result = run(execute_metadata_filter(status="NOPE", db_session=_FakeSession([])))
    assert "not a valid status" in result[0]["error"]


def test_metadata_filter_binds_parameters_not_interpolation():
    session = _FakeSession([])
    run(
        execute_metadata_filter(
            filename_contains="'; DROP TABLE documents; --",
            db_session=session,
        )
    )
    # The dangerous text must arrive as a bound value, absent from the SQL text.
    assert "DROP TABLE" not in session.sql
    assert session.params["filename"] == "'; DROP TABLE documents; --"


def test_metadata_filter_normalises_the_file_type():
    session = _FakeSession([])
    run(execute_metadata_filter(file_type=".PDF", db_session=session))
    assert session.params["file_type"] == "pdf"


def test_metadata_filter_skips_rows_with_an_unusable_document_id():
    """A non-UUID id would break a follow-up doc_inspector call."""
    session = _FakeSession(
        [
            {
                "document_id": "not-a-uuid",
                "filename": "a.pdf",
                "file_type": "pdf",
                "status": "COMPLETED",
                "error_message": None,
                "chunk_count": 1,
            }
        ]
    )

    result = run(execute_metadata_filter(db_session=session))

    assert "note" in result[0]


def test_metadata_filter_only_exposes_errors_for_failed_documents():
    """error_message can carry provider text, so it is not a general field."""
    session = _FakeSession(
        [
            {
                "document_id": str(uuid.uuid4()),
                "filename": "a.pdf",
                "file_type": "pdf",
                "status": "COMPLETED",
                "error_message": "should not appear",
                "chunk_count": 1,
            }
        ]
    )

    result = run(execute_metadata_filter(db_session=session))

    assert "error_message" not in result[0]


# -------------------------------------------------------------- web search


def test_web_search_handles_empty_query():
    assert "error" in run(execute_web_search(""))


def test_web_search_truncates_page_text(monkeypatch):
    """Untruncated page text would blow out the context window."""
    import backend.app.tools.web_search as ws

    class FakeClient:
        def search(self, query, search_depth, max_results):
            return {"results": [{"title": "t", "url": "u", "content": "x" * 9000}]}

    monkeypatch.setattr(ws, "tavily_client", FakeClient())

    result = run(ws.execute_web_search("q"))

    assert len(result["results"][0]["content"]) <= ws.MAX_CONTENT_CHARS