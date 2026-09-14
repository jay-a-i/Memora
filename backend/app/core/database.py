# app/core/database.py

""" IMPORTS """

from app.core.config import settings 

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    create_async_engine,   
    AsyncSession,        
    async_sessionmaker   
)

""" Initializing connection with Database """

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    pool_size=20,       
    max_overflow=10,   
    pool_pre_ping=True  
)

""" Creatinng session"""

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
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