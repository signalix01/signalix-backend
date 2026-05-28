"""
Database Session Management

Provides the async SQLAlchemy engine, session factory, and FastAPI dependency
for database access across all services.

Usage:
    from shared.database.session import get_db, AsyncSessionLocal, engine

    # As FastAPI dependency
    @app.get("/items")
    async def list_items(db: AsyncSession = Depends(get_db)):
        ...

    # Direct session usage
    async with AsyncSessionLocal() as session:
        ...
"""

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from shared.config.settings import settings

logger = logging.getLogger(__name__)


def _create_engine() -> AsyncEngine:
    """Create the async SQLAlchemy engine with production-grade pool settings."""
    return create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG and settings.ENVIRONMENT == "development",
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        pool_recycle=3600,
        pool_timeout=30,
        connect_args={
            "server_settings": {"application_name": "signalixai-backend"},
            "statement_cache_size": 0,
        }
        if "postgresql" in settings.DATABASE_URL
        else {},
    )


# Global engine instance
engine: AsyncEngine = _create_engine()

# Session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async database session.

    The session is automatically closed after the request completes.
    Commits must be handled explicitly by the caller.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def dispose_engine() -> None:
    """Dispose the global engine (call on app shutdown)."""
    global engine
    if engine:
        await engine.dispose()
        logger.info("Database engine disposed")
