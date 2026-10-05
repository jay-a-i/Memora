-- LangGraph checkpoint tables — apply to the EXISTING database.
--
-- Only needed if you would rather create them by hand. The application also
-- creates them itself: AsyncPostgresSaver.setup() runs these same migrations on
-- startup, so this file is a convenience, not a prerequisite.
--
-- Safe to run more than once — every statement is guarded.
--
--   psql "$DATABASE_URL" -f backend/app/db/migrate_checkpoint_tables.sql
--
-- Two changes beyond the new tables, both idempotent:
--   * chat_sessions.title gains NOT NULL, matching the ORM. Without it a row
--     inserted by raw SQL can carry NULL and fail response validation with a 500.
--   * the HNSW index on document_chunks is created if it is missing. It is
--     created non-concurrently because this runs outside a transaction.

BEGIN;

-- ---------------------------------------------------------------------------
-- New: agent state, one row-set per conversation, keyed by chat session UUID.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS checkpoint_migrations (
    v INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE TABLE IF NOT EXISTS checkpoint_blobs (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL,
    version TEXT NOT NULL,
    type TEXT NOT NULL,
    blob BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);

CREATE TABLE IF NOT EXISTS checkpoint_writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    type TEXT,
    blob BYTEA NOT NULL,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

ALTER TABLE checkpoint_blobs ALTER COLUMN blob DROP NOT NULL;
ALTER TABLE checkpoint_writes ADD COLUMN IF NOT EXISTS task_path TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS checkpoints_thread_id_idx ON checkpoints(thread_id);
CREATE INDEX IF NOT EXISTS checkpoint_blobs_thread_id_idx ON checkpoint_blobs(thread_id);
CREATE INDEX IF NOT EXISTS checkpoint_writes_thread_id_idx ON checkpoint_writes(thread_id);

-- ---------------------------------------------------------------------------
-- Existing-table fixes. Each is guarded, so re-running changes nothing.
-- ---------------------------------------------------------------------------

-- Tighter than the ORM already enforces; no-op when the column is already
-- NOT NULL or the table does not exist yet.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'chat_sessions' AND column_name = 'title'
          AND is_nullable = 'YES'
    ) THEN
        ALTER TABLE chat_sessions ALTER COLUMN title SET NOT NULL;
    END IF;
END
$$;

-- Without this index, hybrid_search's `ORDER BY embedding <=> :vector` is a
-- full scan of document_chunks on every query.
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON document_chunks
USING hnsw (embedding vector_cosine_ops);

COMMIT;
