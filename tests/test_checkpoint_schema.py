"""
Guards the checkpoint DDL committed to schema.sql against drift.

The saver's setup() applies the migrations shipped inside the
langgraph-checkpoint-postgres package. schema.sql documents the same tables, and
the two must agree: if they diverge, the app appears configured correctly while
every save fails at runtime with a missing-column error that no local test would
surface.

These read the installed package rather than a hardcoded copy, so upgrading the
package and forgetting to update schema.sql is caught here.
"""

import pathlib
import re

import pytest

pytest.importorskip(
    "langgraph.checkpoint.postgres",
    reason="langgraph-checkpoint-postgres is not installed",
)

from langgraph.checkpoint.postgres.base import BasePostgresSaver  # noqa: E402

SCHEMA_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "backend/app/db/schema.sql"
)

CHECKPOINT_TABLES = {
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoint_migrations",
}


def _tables_and_columns(ddl: str) -> dict[str, set[str]]:
    """Extracts {table: {column, ...}} from CREATE TABLE statements."""
    out: dict[str, set[str]] = {}
    for match in re.finditer(
        r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\n\);", ddl, re.S
    ):
        table, body = match.group(1), match.group(2)
        cols = set()
        for line in body.splitlines():
            line = line.strip().rstrip(",")
            if not line or line.startswith(("PRIMARY KEY", "CONSTRAINT", "UNIQUE")):
                continue
            cols.add(line.split()[0])
        out[table] = cols
    return out


@pytest.fixture(scope="module")
def schema_ddl() -> str:
    return SCHEMA_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def package_ddl() -> str:
    return "\n".join(BasePostgresSaver.MIGRATIONS)


class TestSchemaMatchesPackage:
    def test_all_checkpoint_tables_are_documented(self, schema_ddl):
        tables = _tables_and_columns(schema_ddl)
        missing = CHECKPOINT_TABLES - set(tables)
        assert not missing, f"schema.sql is missing {sorted(missing)}"

    @pytest.mark.parametrize("table", sorted(CHECKPOINT_TABLES))
    def test_columns_match_the_package_migrations(self, schema_ddl, package_ddl, table):
        pkg = _tables_and_columns(package_ddl).get(table, set())
        repo = _tables_and_columns(schema_ddl).get(table, set())
        # task_path arrives via a later ALTER rather than the CREATE TABLE, and
        # schema.sql applies that ALTER too, so compare against both forms.
        assert pkg <= repo, (
            f"{table}: schema.sql is missing columns the package creates: "
            f"{sorted(pkg - repo)}"
        )

    def test_blob_column_is_nullable(self, schema_ddl):
        # A later package migration drops NOT NULL on this column; without it a
        # checkpoint write that stores no blob fails.
        assert (
            "ALTER TABLE checkpoint_blobs ALTER COLUMN blob DROP NOT NULL"
            in schema_ddl
        )

    def test_task_path_column_is_added(self, schema_ddl):
        # checkpoint_writes gained task_path in a later migration and the saver's
        # INSERT statements name it.
        assert "task_path" in schema_ddl

    def test_thread_id_indexes_exist(self, schema_ddl):
        # Every read and write filters by thread_id, so its absence turns each
        # checkpoint operation into a sequential scan of the table.
        for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            assert f"{table}_thread_id_idx" in schema_ddl


class TestSchemaStaysIdempotent:
    def test_every_create_index_is_guarded(self, schema_ddl):
        """
        Re-applying schema.sql must be a no-op. One unguarded CREATE INDEX made
        the file abort on a database that already had the tables, so it could
        never be re-run.
        """
        for line in schema_ddl.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("CREATE INDEX") or stripped.upper().startswith(
                "CREATE UNIQUE INDEX"
            ):
                assert "IF NOT EXISTS" in stripped.upper(), (
                    f"unguarded index statement: {stripped}"
                )

    def test_checkpoint_statements_are_guarded(self, schema_ddl):
        for match in re.finditer(
            r"^\s*(CREATE TABLE|CREATE INDEX|ALTER TABLE)\s+(?!IF NOT EXISTS)(.{0,60})",
            schema_ddl,
            re.MULTILINE | re.IGNORECASE,
        ):
            statement = match.group(0).strip()
            # ADD COLUMN IF NOT EXISTS carries its own guard mid-statement.
            if statement.upper().startswith("ALTER TABLE"):
                assert "IF NOT EXISTS" in statement.upper() or "DROP NOT NULL" in statement.upper(), statement
            else:
                assert "IF NOT EXISTS" in statement.upper(), statement
