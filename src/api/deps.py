"""Shared FastAPI dependencies.

Provides the canonical database session dependency used by all route files.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Get database session from app state via FastAPI dependency injection.

    Yields a session from the async session factory stored in app.state.
    The session is scoped to the request lifecycle.
    """
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        yield session
