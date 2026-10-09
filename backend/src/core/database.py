# app/core/database.py

""" IMPORTS """
import logging
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)

from src.core.config import settings
from src.core.errors import client_message

logger = logging.getLogger(__name__)


""" Initializing connection with Database """

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=1800,
)

""" Creatinng session"""

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yields an active database session per request.
    Automatically commits on success or rolls back if an exception occurs.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def check_db_health(session: AsyncSession | None = None):
    """
    Pings the database with 'SELECT 1' to ensure the connection pool and engine are responsive.
    """
    stmt = text("SELECT 1")
    try:
        if session:
            await session.execute(stmt)
        else:
            async with AsyncSessionLocal() as db:
                await db.execute(stmt)
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.exception("Database health check failed")
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": client_message(e),
        }
