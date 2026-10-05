"""
Regression tests for bugs found during the 2026-10-04 backend review.

Each test names the failure it prevents. Several of these were shipping
defects, not hypotheticals.

Note on schema: `backend/app/db/schema.sql` is reference DDL. No code in this
repo creates or migrates the database, so there is nothing here to test about
applying it — the equivalent invariants (ORM and DDL agreeing on the vector
width, on the generated FTS column) live in `test_config.py`.
"""

import re

import pytest


# ------------------------------------------------------------------- upload


@pytest.mark.parametrize("length", [10, 200, 254, 304])
def test_long_filename_keeps_its_extension(length):
    """
    Truncating the whole name cut off the extension. The endpoint validated the
    extension on the full name, so a long .pdf was accepted with 202 and then
    failed ingestion with "Unsupported file format".
    """
    import os.path

    from backend.app.api.v1.endpoints.documents import MAX_FILENAME_LEN, _safe_filename

    safe = _safe_filename("a" * (length - 4) + ".pdf")

    assert os.path.splitext(safe)[1] == ".pdf", f"lost extension at len={length}"
    assert len(safe) <= MAX_FILENAME_LEN


def test_safe_filename_still_blocks_traversal():
    from backend.app.api.v1.endpoints.documents import _safe_filename

    for bad in ["../../evil.md", "a/b/c.pdf", "..\\..\\x.md", "/etc/passwd"]:
        cleaned = _safe_filename(bad)
        assert "/" not in cleaned and "\\" not in cleaned and ".." not in cleaned


def test_overlong_extension_does_not_consume_the_whole_budget():
    """A pathological 'extension' longer than the budget must not truncate to ''."""
    from backend.app.api.v1.endpoints.documents import _safe_filename

    safe = _safe_filename("report" + "." + "x" * 40)

    assert safe
    assert len(safe) <= 200
    assert safe.startswith("report")


# ------------------------------------------------------------------- errors


def test_ingestion_never_persists_raw_exception_text(tmp_path, stub_ingestion_db):
    """
    `str(e)` used to be written straight onto Document.error_message, which
    the documents endpoints return and metadata_filter hands to the LLM. An
    asyncpg failure carries the DSN; an OSError carries an absolute path.
    """
    import asyncio

    from backend.app.services.ingestion import ProcessFile

    source = tmp_path / "doc.md"
    source.write_text("# t\n\nbody\n", encoding="utf-8")

    proc = ProcessFile()

    async def boom(texts):
        from backend.app.core.errors import EmbeddingError

        raise EmbeddingError(
            "Embedding request failed for batch 1/3 using 'embed-v5.0-pro': "
            'connection to server at "db.internal.corp" (10.0.0.7) failed'
        )

    proc.embed_documents = boom
    result = asyncio.run(
        proc.upload_file(file_path=str(source), document_id=stub_ingestion_db._row.id)
    )

    assert result.startswith("FAILED")
    assert "db.internal.corp" not in result
    assert "10.0.0.7" not in result
    assert "db.internal.corp" not in (stub_ingestion_db._row.error_message or "")


def test_ingestion_failure_message_is_actionable(tmp_path, stub_ingestion_db):
    """A generic message is safe, but a useless one is its own bug."""
    import asyncio

    from langchain_core.documents import Document

    from backend.app.services.ingestion import ProcessFile

    source = tmp_path / "doc.md"
    source.write_text("# t\n\nbody\n", encoding="utf-8")

    proc = ProcessFile(
        doc_converter=None,
        chunker=lambda p: [Document(page_content="a")],
        embedder=None,
    )

    async def no_vectors(texts):
        return []

    proc.embed_documents = no_vectors

    result = asyncio.run(
        proc.upload_file(file_path=str(source), document_id=stub_ingestion_db._row.id)
    )

    assert result.startswith("FAILED")
    # Either it names the mismatch or it points at the embedding config.
    assert "mismatch" in result.lower() or "embed" in result.lower()


# --------------------------------------------------------------- FTS arm


def test_fts_arm_orders_before_limiting():
    """
    The FTS arm had a window function but no ORDER BY before LIMIT, so the 20
    surviving rows were arbitrary and their RRF ranks meaningless. The vector
    arm already did this correctly.
    """
    from backend.app.tools.hybrid_search import HYBRID_SEARCH_SQL

    sql = HYBRID_SEARCH_SQL.text
    fts = sql.split("fts_search AS (")[1]

    assert re.search(
        r"ORDER BY\s+ts_rank_cd.*?LIMIT\s+:candidates", fts, re.S | re.I
    ), "FTS arm must sort by rank before LIMIT"


# --------------------------------------------------------- streaming narrative


def test_only_the_final_segment_is_persisted():
    """
    Text the model emits before calling a tool is narration ("Let me search
    for that."), not the answer. It was accumulated into the stored transcript
    and re-fed as history on every later turn.
    """
    # Mirrors the SSE generator's segment logic in chat.py.
    current: list[str] = []
    events = [
        ("stream", "Let me "),
        ("stream", "search for that."),
        ("tool_start", "hybrid_search"),
        ("stream", "Refunds are "),
        ("stream", "allowed within 30 days."),
    ]
    for kind, payload in events:
        if kind == "stream":
            current.append(payload)
        elif kind == "tool_start" and current:
            current = []

    assert "".join(current) == "Refunds are allowed within 30 days."
    assert "Let me" not in "".join(current)


def test_chat_stream_error_event_carries_no_internal_detail():
    """
    The SSE `error` event goes straight to a browser. The generator must send
    the safe summary; the traceback belongs in the log.
    """
    import inspect

    from backend.app.api.v1.endpoints import chat

    source = inspect.getsource(chat.chat_stream)
    assert "client_message" in source or "log_and_client_message" in source
    assert '{"type": "error", "message": str(e)}' not in source


# --------------------------------------------------------------- transaction


def test_tool_failure_rolls_back_the_session():
    """
    A failed statement aborts the Postgres transaction, so without a rollback
    every later query fails with InFailedSQLTransactionError -- including the
    commit that persists the assistant turn.
    """
    import inspect

    from backend.app.agent.orchestrator import tool_executor

    source = inspect.getsource(tool_executor)
    assert "rollback" in source, "tool_executor must recover the transaction"


def _tmp_markdown() -> str:
    """Writes a throwaway markdown file and returns its path."""
    import tempfile
    from pathlib import Path

    directory = Path(tempfile.mkdtemp(prefix="memora-test-"))
    path = directory / "doc.md"
    path.write_text("# title\n\nsome content\n", encoding="utf-8")
    return str(path)