# backend/app/agent/checkpointer.py

"""
Postgres-backed LangGraph checkpointer.

Why this exists
---------------
The agent previously kept no state of its own: every request re-sent the whole
transcript, and the graph was compiled with no checkpointer so a run started
from nothing every time. That put the burden of memory entirely on the caller.

With a checkpointer, LangGraph persists the agent state after every node, and
the next run for the same `thread_id` resumes from it. The agent therefore
recovers its own prior messages -- including the tool calls and tool results
from earlier cycles -- without the endpoint having to replay them.

`thread_id` is the chat session UUID, so one conversation is one thread and two
conversations never share state.

Connections
-----------
The saver speaks psycopg3, not asyncpg, so it gets its own connection pool
derived from the same DATABASE_URL. The URL is rewritten because SQLAlchemy's
"+asyncpg" driver suffix is meaningless to psycopg.

Lifecycle
---------
The pool is opened once at application startup and closed at shutdown. Building
the saver at import time would open a connection during module import, which
breaks tests and any process that imports the app without serving it.
"""

import asyncio
import logging
import sys
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

# The checkpointer talks psycopg3. Both of these are the SQLAlchemy spellings of
# a plain Postgres URL; neither driver suffix means anything to psycopg.
_ASQLALCHEMY_SCHEMES = (
    "postgresql+asyncpg://",
    "postgresql+psycopg://",
    "postgresql+psycopg2://",
)

# psycopg's async support requires a selector-style event loop. Windows defaults
# to ProactorEventLoop, which psycopg rejects outright, so on win32 every
# connection attempt raises InterfaceError no matter how the DSN is configured.
# SQLAlchemy's asyncpg engine has the opposite requirement and works fine on
# Proactor, so this is a psycopg-only constraint and the two drivers genuinely
# cannot share the default loop on Windows.
_SELECTOR_LOOP_HINT = (
    "The LangGraph checkpointer needs a selector-style event loop on Windows "
    "(psycopg cannot use ProactorEventLoop). Either set CHECKPOINT_ENABLED=false "
    "to run without agent state persistence, or start the server with "
    "uvicorn --loop asyncio and a WindowsSelectorEventLoop policy, e.g. via "
    "asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy()) "
    "before uvicorn starts."
)


def psycopg_loop_is_compatible() -> bool:
    """
    Reports whether the running loop can drive psycopg's async connections.

    Checked before opening the pool so the failure is a single actionable log
    line, instead of a retry storm from the pool followed by a generic
    "internal error" that looks like a database problem.
    """
    if sys.platform != "win32":
        return True
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No loop yet; the one that starts us will be judged at connect time.
        return True
    return not isinstance(loop, asyncio.ProactorEventLoop)


def psycopg_dsn(database_url: str) -> str:
    """Strips the SQLAlchemy driver suffix so psycopg can parse the URL."""
    for scheme in _ASQLALCHEMY_SCHEMES:
        if database_url.startswith(scheme):
            return database_url.replace(scheme, "postgresql://", 1)
    return database_url


def thread_id_for(session_id: Any) -> str:
    """
    Maps a chat session to its LangGraph thread.

    The column is TEXT, so a UUID object is stringified here rather than at each
    call site. `_get_or_create_session` may hand back either a UUID or a str
    depending on whether the row already existed, and the two must produce the
    same thread id or a resumed conversation would silently start fresh.
    """
    return str(session_id)


class CheckpointerManager:
    """
    Owns the checkpointer's connection pool for the life of the process.

    Held as a module-level singleton because the compiled graph captures the
    saver instance at import time; there is no way to swap it afterwards.
    """

    def __init__(self) -> None:
        self._pool: AsyncConnectionPool | None = None
        self._saver: AsyncPostgresSaver | None = None

    @property
    def saver(self) -> AsyncPostgresSaver | None:
        """The saver, or None when checkpointing is off or failed to start."""
        return self._saver

    async def start(self) -> AsyncPostgresSaver | None:
        """
        Opens the pool and runs the checkpointer's migrations.

        Returns None (rather than raising) when checkpointing is disabled or the
        database is unreachable: the agent still works without persistence, it
        just falls back to the caller-supplied history. A hard failure here
        would take down an app whose chat endpoint is otherwise fine.
        """
        if not settings.CHECKPOINT_ENABLED:
            logger.info("LangGraph checkpointing disabled by configuration.")
            return None

        if not psycopg_loop_is_compatible():
            # Failing fast here rather than letting the pool retry: on Windows
            # this can never succeed, and the pool's retries buried the real
            # cause under connection warnings.
            logger.error("LangGraph checkpointing unavailable. %s", _SELECTOR_LOOP_HINT)
            return None

        if self._saver is not None:
            return self._saver

        dsn = psycopg_dsn(settings.DATABASE_URL)
        try:
            pool = AsyncConnectionPool(
                conninfo=dsn,
                min_size=1,
                max_size=settings.CHECKPOINT_POOL_SIZE,
                timeout=settings.CHECKPOINT_TIMEOUT,
                open=False,
            )
            await pool.open(wait=True, timeout=settings.CHECKPOINT_TIMEOUT)

            saver = AsyncPostgresSaver(pool)
            # Idempotent: each migration is guarded, and applied versions are
            # recorded in checkpoint_migrations so re-running is a no-op. This
            # is what creates the four checkpoint_* tables.
            await saver.setup()

            self._pool = pool
            self._saver = saver
            logger.info("LangGraph Postgres checkpointer ready.")
            return saver
        except Exception as e:
            # The exception type is logged because it is the part that
            # distinguishes "database unreachable" from "authentication failed"
            # or "psycopg cannot use this event loop". This log line stays
            # server-side only; nothing here is returned to a client.
            logger.error(
                "Could not start the LangGraph checkpointer (%s: %s); continuing "
                "without agent state persistence. Agent memory falls back to the "
                "transcript the endpoint replays per request.",
                type(e).__name__,
                e,
            )
            # Leave the half-built pool closed so a later attempt is clean.
            if self._pool is not None:
                try:
                    await self._pool.close()
                except Exception:
                    logger.warning("Could not close the checkpointer pool cleanly.")
                self._pool = None
            self._saver = None
            return None

    async def stop(self) -> None:
        """Closes the pool. Safe to call when startup failed or never ran."""
        if self._pool is not None:
            try:
                await self._pool.close()
            except Exception:
                logger.warning("Error closing the checkpointer pool.", exc_info=True)
            self._pool = None
        self._saver = None


checkpointer_manager = CheckpointerManager()


async def get_checkpointer() -> AsyncPostgresSaver | None:
    """
    Returns the shared saver, starting the pool on first use.

    Callers that run outside the app's lifespan (a script, a test) get the pool
    started lazily here rather than assuming startup already happened.
    """
    if checkpointer_manager.saver is None:
        await checkpointer_manager.start()
    return checkpointer_manager.saver
