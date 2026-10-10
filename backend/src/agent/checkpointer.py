import logging
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from src.core.config import settings

logger = logging.getLogger(__name__)

_ASQLALCHEMY_SCHEMES = (
    "postgresql+asyncpg://",
    "postgresql+psycopg://",
    "postgresql+psycopg2://",
)


def psycopg_dsn(database_url: str) -> str:
    #psycopg need encoded db URL
    database_url = database_url.replace(" ", "%20").replace("(", "%28").replace(")", "%29")
    for scheme in _ASQLALCHEMY_SCHEMES:
        if database_url.startswith(scheme):
            return database_url.replace(scheme, "postgresql://", 1)
    return database_url


def thread_id_for(session_id: Any) -> str:
    return str(session_id)


class CheckpointerManager:
    def __init__(self) -> None:
        self._pool: AsyncConnectionPool | None = None
        self._saver: AsyncPostgresSaver | None = None

    @property
    def saver(self) -> AsyncPostgresSaver | None:
        return self._saver

    async def start(self) -> AsyncPostgresSaver | None:
        if not settings.CHECKPOINT_ENABLED:
            logger.info("LangGraph checkpointing disabled by configuration.")
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
            await pool.open(wait=True, timeout=settings.CHECKPOINTER_TIMEOUT)

            saver = AsyncPostgresSaver(pool)
            await saver.setup()

            self._pool = pool
            self._saver = saver
            logger.info("LangGraph Postgres checkpointer ready.")
            return saver
        except Exception as e:
            logger.error(
                "Could not start the LangGraph checkpointer (%s: %s); continuing "
                "without agent state persistence. Agent memory falls back to the "
                "transcript the endpoint replays per request.",
                type(e).__name__,
                e,
            )
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
    if checkpointer_manager.saver is None:
        await checkpointer_manager.start()
    return checkpointer_manager.saver