from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.config import get_settings


def normalize_database_url(database_url: str) -> str:
    """Normalize database URLs to async drivers."""

    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    if database_url.startswith("sqlite:///"):
        return database_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)

    return database_url


class DatabaseSessionManager:
    """Manage the async SQLAlchemy engine and session factory."""

    def __init__(self, database_url: str):
        self.database_url = normalize_database_url(database_url)
        self.engine: AsyncEngine = create_async_engine(self.database_url, future=True)
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session

    async def close(self) -> None:
        await self.engine.dispose()


_default_session_manager: DatabaseSessionManager | None = None


def get_default_session_manager() -> DatabaseSessionManager:
    """Return the application-wide session manager."""

    global _default_session_manager

    if _default_session_manager is None:
        settings = get_settings()
        _default_session_manager = DatabaseSessionManager(settings.database_url)

    return _default_session_manager


async def close_default_session_manager() -> None:
    """Dispose the application-wide engine if it was created."""

    global _default_session_manager

    if _default_session_manager is not None:
        await _default_session_manager.close()
        _default_session_manager = None


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a database session."""

    session_manager = get_default_session_manager()
    async with session_manager.session() as session:
        yield session
