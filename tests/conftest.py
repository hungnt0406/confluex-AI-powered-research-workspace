from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.api.dependencies import get_db_session
from backend.db.base import Base
from backend.db.models import Project, User
from backend.main import create_app
from backend.security import create_access_token, hash_password


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def session_factory(
    tmp_path: Path,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    database_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}", future=True)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def app(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator:
    test_app = create_app()

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    test_app.dependency_overrides[get_db_session] = override_get_db_session
    yield test_app
    test_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


@pytest_asyncio.fixture
async def sample_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, str]:
    async with session_factory() as session:
        user = User(email="researcher@example.com", hashed_password=hash_password("supersecret123"))
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return {"id": user.id, "email": user.email}


@pytest_asyncio.fixture
async def sample_project(
    session_factory: async_sessionmaker[AsyncSession],
    sample_user: dict[str, str],
) -> dict[str, str]:
    async with session_factory() as session:
        project = Project(
            user_id=sample_user["id"],
            title="AI Literature Review",
            topic_description="Survey multi-agent literature review systems.",
            citation_format="APA",
            year_start=2018,
            candidate_limit=60,
            summary_limit=30,
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return {"id": project.id, "title": project.title}


@pytest_asyncio.fixture
async def auth_headers(sample_user: dict[str, str]) -> dict[str, str]:
    token = create_access_token(sample_user["id"])
    return {"Authorization": f"Bearer {token}"}
