"""Ingestion pipeline with stubbed conversion, chunking, and embedding."""

import asyncio
import uuid
from pathlib import Path

import pytest
from langchain_core.documents import Document

from backend.app.services.chunking import chunk_text
from backend.app.services.doc_to_md import docx_to_md
from backend.app.services.ingestion import ProcessFile


# ---------------------------------------------------------------- chunking


def test_chunk_text_splits_and_drops_blanks(tmp_path, monkeypatch):
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "CHUNK_SIZE", 60)
    monkeypatch.setattr(settings, "CHUNK_OVERLAP", 10)

    md = tmp_path / "doc.md"
    md.write_text("# Title\n\n## Section\n\n" + ("word " * 200), encoding="utf-8")

    chunks = chunk_text(str(md))
    assert chunks
    assert all(c.page_content.strip() for c in chunks)
    assert all(len(c.page_content) <= 60 + 60 for c in chunks)


def test_chunk_text_returns_empty_for_blank_file(tmp_path):
    md = tmp_path / "empty.md"
    md.write_text("   \n\n  ", encoding="utf-8")
    assert chunk_text(str(md)) == []


def test_chunk_text_preserves_header_metadata(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("# Alpha\n\ntext one\n\n## Beta\n\ntext two\n", encoding="utf-8")

    chunks = chunk_text(str(md))
    headers = {c.metadata.get("Header 1") for c in chunks} | {
        c.metadata.get("Header 2") for c in chunks
    }
    assert {"Alpha", "Beta"} & headers


# --------------------------------------------------------------- conversion


def test_docx_is_parsed_not_read_as_raw_text(tmp_path):
    """A .docx is a ZIP; reading it as text would embed binary noise."""
    docx = pytest.importorskip("docx")

    src = tmp_path / "sample.docx"
    out = tmp_path / "out.md"

    d = docx.Document()
    d.add_heading("Quarterly Report", level=1)
    d.add_paragraph("Revenue grew.")
    d.add_heading("Details", level=2)
    table = d.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Region"
    table.cell(0, 1).text = "Total"
    d.save(str(src))

    result = docx_to_md(str(src), output_md=str(out))
    assert result is not None, "conversion failed"

    text = out.read_text(encoding="utf-8")
    assert "# Quarterly Report" in text  # heading mapped
    assert "## Details" in text  # subheading mapped
    assert "| Region | Total |" in text  # table rendered
    assert "\x00" not in text  # not raw ZIP bytes


def test_docx_with_no_text_returns_none(tmp_path):
    docx = pytest.importorskip("docx")

    src = tmp_path / "empty.docx"
    docx.Document().save(str(src))

    assert docx_to_md(str(src), output_md=str(tmp_path / "o.md")) is None


def test_unreadable_pdf_conversion_returns_none(tmp_path):
    """doc_to_md reports failure rather than raising, so the caller controls it."""
    from backend.app.services.doc_to_md import doc_to_md

    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"this is not a pdf")

    assert doc_to_md(str(broken), output_md=str(tmp_path / "o.md")) is None


# ------------------------------------------------------------------ pipeline


def test_ingestion_stops_when_document_row_is_missing(tmp_path, missing_document_row):
    """A missing document row short-circuits before any conversion work."""
    proc = ProcessFile()
    result = asyncio.run(
        proc.upload_file(file_path=str(tmp_path / "x.pdf"), document_id=uuid.uuid4())
    )
    assert result.startswith("FAILED")
    assert "not found in database" in result


def test_ingestion_rejects_unparseable_filename_when_id_missing(tmp_path):
    proc = ProcessFile()
    result = asyncio.run(proc.upload_file(file_path=str(tmp_path / "not-a-uuid_file.pdf")))
    assert "Could not parse document ID" in result


def test_unsupported_extension_is_reported_as_a_safe_error(tmp_path, stub_ingestion_db):
    """The message reaches the API, so it must not be raw exception text."""
    proc = ProcessFile()
    source = tmp_path / "doc.exe"
    source.write_text("x", encoding="utf-8")

    result = asyncio.run(
        proc.upload_file(file_path=str(source), document_id=stub_ingestion_db._row.id)
    )

    assert result.startswith("FAILED")
    assert "Unsupported file format" in result
    assert ".exe" in result


def test_ingestion_cleans_up_temp_files_on_failure(tmp_path):
    """Cleanup must happen on every exit path, not just the happy one."""
    source = tmp_path / "doc.md"
    source.write_text("# hi\n\ncontent", encoding="utf-8")

    proc = ProcessFile(
        doc_converter=None,
        chunker=lambda p: [Document(page_content="a"), Document(page_content="b")],
        embedder=None,
    )

    async def boom(texts):
        raise RuntimeError("no embeddings")

    proc.embed_documents = boom
    result = asyncio.run(proc.upload_file(file_path=str(source), document_id=uuid.uuid4()))

    assert result.startswith("FAILED")
    assert not source.exists(), "temp file was not cleaned up"


def test_ingestion_cleans_up_converted_markdown(tmp_path):
    """PDF conversion writes a sibling .md; it must not outlive the run."""
    source = tmp_path / "doc.pdf"
    source.write_bytes(b"%PDF-1.4 fake")

    def fake_converter(file_path, output_md=None, image_dir=None, extract_images=None):
        Path(output_md).write_text("# converted", encoding="utf-8")
        return {"output_md": output_md, "image_dir": image_dir}

    proc = ProcessFile(doc_converter=fake_converter, embedder=None)

    async def no_embeddings(texts):
        return []

    proc.embed_documents = no_embeddings
    result = asyncio.run(proc.upload_file(file_path=str(source), document_id=uuid.uuid4()))

    assert result.startswith("FAILED")
    assert not list(tmp_path.glob("*_converted.md")), "converted file was left behind"


def test_embedding_count_mismatch_is_caught(tmp_path):
    """
    A provider returning the wrong number of vectors would otherwise zip
    silently against the chunks and store a partial document.
    """
    source = tmp_path / "doc.md"
    source.write_text("# t\n\nbody\n", encoding="utf-8")

    async def one_embedding(texts):
        return [[0.0] * 1536]

    proc = ProcessFile(
        doc_converter=None,
        chunker=lambda p: [Document(page_content="a"), Document(page_content="b")],
        embedder=None,
    )
    proc.embed_documents = one_embedding

    result = asyncio.run(proc.upload_file(file_path=str(source), document_id=uuid.uuid4()))

    assert result.startswith("FAILED")
    assert "mismatch" in result.lower()


def test_embedding_failure_is_reported_without_provider_detail(tmp_path):
    """A provider error can echo the request; only our own text may cross."""
    from backend.app.core.errors import EmbeddingError

    source = tmp_path / "doc.md"
    source.write_text("# t\n\nbody\n", encoding="utf-8")

    async def boom(texts):
        # Shaped exactly as embeddingV2 raises it.
        raise EmbeddingError(
            "Embedding request failed for batch 1/2 using 'embed-v5.0-pro': "
            "401 Unauthorized for url https://api.cohere.com/v2/embed"
        )

    proc = ProcessFile(doc_converter=None, embedder=None)
    proc.embed_documents = boom

    result = asyncio.run(proc.upload_file(file_path=str(source), document_id=uuid.uuid4()))

    assert result.startswith("FAILED")
    assert "cohere.com" not in result
    assert "401" not in result
    assert "embed" in result.lower()


def test_failed_document_is_marked_failed_on_its_row(tmp_path, stub_ingestion_db):
    """The row must leave PROCESSING; that is what the documents list shows."""
    source = tmp_path / "doc.md"
    source.write_text("# t\n\nbody\n", encoding="utf-8")

    async def boom(texts):
        raise RuntimeError("no embeddings")

    proc = ProcessFile(doc_converter=None, embedder=None)
    proc.embed_documents = boom

    row = stub_ingestion_db._row
    asyncio.run(proc.upload_file(file_path=str(source), document_id=row.id))

    assert row.status == "FAILED"
    assert row.error_message
    assert "no embeddings" not in row.error_message


def test_successful_ingestion_marks_the_row_completed(tmp_path, stub_ingestion_db):
    from backend.app.db.models.document import DocumentChunk

    source = tmp_path / "doc.md"
    source.write_text("# t\n\nbody\n", encoding="utf-8")

    async def embeddings(texts):
        return [[0.0] * 1536 for _ in texts]

    proc = ProcessFile(
        doc_converter=None,
        chunker=lambda p: [Document(page_content="a"), Document(page_content="b")],
        embedder=None,
    )
    proc.embed_documents = embeddings

    row = stub_ingestion_db._row
    result = asyncio.run(proc.upload_file(file_path=str(source), document_id=row.id))

    assert result.startswith("SUCCESS")
    assert row.status == "COMPLETED"
    assert row.error_message is None
    assert len(stub_ingestion_db.added) == 2
    assert all(isinstance(r, DocumentChunk) for r in stub_ingestion_db.added)


def _write_md() -> str:
    import tempfile

    directory = Path(tempfile.mkdtemp(prefix="memora-test-"))
    path = directory / "doc.md"
    path.write_text("# t\n\nbody\n", encoding="utf-8")
    return str(path)