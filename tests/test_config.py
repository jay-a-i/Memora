"""Configuration parsing and validation."""

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.core.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]

BASE = {
    "DATABASE_URL": "postgresql+asyncpg://u:p@localhost:5432/db",
    "OPENROUTER_API_KEY": "or-key",
    "COHERE_API_KEY": "co-key",
    "APP_API_KEY": "secret",
}


def _settings(**overrides):
    return Settings(**{**BASE, **overrides})


# ------------------------------------------------------------------- parsing


def test_cors_origins_accepts_csv():
    s = _settings(CORS_ORIGINS="http://a.test, http://b.test")
    assert s.CORS_ORIGINS == ["http://a.test", "http://b.test"]


def test_cors_origins_accepts_json():
    s = _settings(CORS_ORIGINS='["http://a.test"]')
    assert s.CORS_ORIGINS == ["http://a.test"]


def test_bare_postgres_url_is_upgraded_to_asyncpg():
    # A synchronous URL would fail at connect time with an obscure error.
    s = _settings(DATABASE_URL="postgresql://u:p@localhost:5432/db")
    assert s.DATABASE_URL.startswith("postgresql+asyncpg://")


def test_async_url_is_left_alone():
    assert _settings().DATABASE_URL == BASE["DATABASE_URL"]


# ------------------------------------------------------- credential checks


def test_openrouter_key_is_required():
    with pytest.raises(ValidationError) as exc:
        _settings(OPENROUTER_API_KEY=None)
    assert "OPENROUTER_API_KEY" in str(exc.value)


def test_cohere_key_is_required():
    """Embeddings go through Cohere, so its key is not optional."""
    with pytest.raises(ValidationError) as exc:
        _settings(COHERE_API_KEY=None)
    assert "COHERE_API_KEY" in str(exc.value)


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_model_id_is_rejected_at_startup(blank):
    """
    An `LLM=""` line in app.env sets the variable to an empty string, which
    overrides the default instead of falling back to it. Without a validator the
    app starts and every chat request fails at the provider with a message that
    never mentions configuration.
    """
    with pytest.raises(ValidationError):
        _settings(LLM=blank)
    with pytest.raises(ValidationError):
        _settings(EMBEDDING_MODEL=blank)


def test_model_defaults_are_usable_without_env():
    """The defaults must be real ids, not empty placeholders."""
    s = _settings()
    assert s.LLM.strip()
    assert s.EMBEDDING_MODEL.strip()


# ------------------------------------------------- dimension consistency


def test_default_dimension_matches_schema_sql_column():
    """
    The two widths must agree or inserts fail at ingestion time.

    schema.sql declares `embedding vector(N)` and the ORM reads
    EMBEDDING_DIMENSIONS.
    """
    schema = (REPO_ROOT / "backend" / "app" / "db" / "schema.sql").read_text(
        encoding="utf-8"
    )
    match = re.search(r"embedding\s+vector\((\d+)\)", schema)
    assert match, "could not find vector(N) in schema.sql"

    settings = _settings()
    assert int(match.group(1)) == settings.EMBEDDING_DIMENSIONS, (
        f"schema.sql declares vector({match.group(1)}) but "
        f"EMBEDDING_DIMENSIONS is {settings.EMBEDDING_DIMENSIONS}"
    )


def test_orm_column_width_matches_configured_dimensions():
    from backend.src.db.models.document import DocumentChunk

    column = DocumentChunk.__table__.c.embedding
    assert column.type.dim == _settings().EMBEDDING_DIMENSIONS


def test_orm_fts_column_mirrors_the_ddl():
    """
    schema.sql declares fts_content as a STORED generated column. A plain column
    in the ORM would stay NULL and silently disable the keyword half of
    hybrid_search.
    """
    from backend.src.db.models.document import DocumentChunk

    fts = DocumentChunk.__table__.c.fts_content
    assert fts.computed is not None
    assert fts.computed.persisted is True


# --------------------------------------------------------- live settings


def test_upload_limit_is_a_single_setting():
    """
    Two similarly named upload caps used to exist and only one was enforced, so
    setting the other was a silent no-op.
    """
    s = _settings()
    assert not hasattr(s, "MAX_FILE_UPLOAD_BYTES")
    assert s.MAX_UPLOAD_BYTES > 0