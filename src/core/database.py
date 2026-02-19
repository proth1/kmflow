"""SQLAlchemy 2.x async engine and session factory.

Provides the async engine, session maker, and a dependency-injectable
session generator for FastAPI route handlers.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.core.config import Settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    pass


def create_engine(
    settings: Settings,
) -> tuple[
    AsyncEngine,
    async_sessionmaker[AsyncSession],
]:
    """Create async engine and session factory from settings.

    Returns:
        Tuple of (engine, async_session_factory).
    """
    engine = create_async_engine(
        settings.database_url or "",
        echo=settings.debug,
        pool_size=20,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=300,
    )

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    return engine, session_factory


async def get_db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session and ensure cleanup.

    This is used as a FastAPI dependency to provide a session per request.
    """
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
