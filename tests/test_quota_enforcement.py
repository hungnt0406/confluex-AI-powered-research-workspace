import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.agents.state import AgentState
from backend.api.dependencies import get_deep_search_service, get_pipeline_service
from backend.config import get_settings
from backend.db.models import CreditTransaction, Project, User
from backend.security import create_access_token, hash_password
from backend.services.deep_search import DeepSearchStreamEvent


async def create_user_and_project(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    email: str,
    credit_balance: int,
) -> tuple[User, Project]:
    async with session_factory() as session:
        user = User(
            email=email,
            hashed_password=hash_password("supersecret123"),
            credit_balance=credit_balance,
        )
        session.add(user)
        await session.flush()

        project = Project(
            user_id=user.id,
            title="Quota Test Project",
            topic_description="Test quota enforcement for the pipeline route.",
            citation_format="APA",
            year_start=2020,
            candidate_limit=20,
            summary_limit=10,
        )
        session.add(project)
        await session.commit()
        await session.refresh(user)
        await session.refresh(project)
        return user, project


@pytest.mark.asyncio
async def test_pipeline_route_returns_402_when_user_has_insufficient_credits(
    client,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user, project = await create_user_and_project(
        session_factory,
        email="quota-empty@example.com",
        credit_balance=0,
    )
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}

    response = await client.post(f"/projects/{project.id}/run", headers=headers)

    assert response.status_code == 402
    assert response.json() == {
        "detail": "Insufficient credits.",
        "required": 20,
        "balance": 0,
    }


@pytest.mark.asyncio
async def test_pipeline_route_debits_credits_on_success(
    app,
    client,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user, project = await create_user_and_project(
        session_factory,
        email="quota-success@example.com",
        credit_balance=50,
    )
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}

    class FakePipelineService:
        async def run_project(self, *, session, project) -> AgentState:
            return AgentState(
                project_id=project.id,
                topic=project.topic_description,
                queries=["quota enforcement"],
                raw_papers=[],
                ranked_papers=[],
                summaries=[],
                qa_flags=[],
                errors=[],
            )

    app.dependency_overrides[get_pipeline_service] = lambda: FakePipelineService()
    response = await client.post(f"/projects/{project.id}/run", headers=headers)
    app.dependency_overrides.pop(get_pipeline_service, None)

    assert response.status_code == 200

    async with session_factory() as session:
        persisted_user = await session.get(User, user.id)
        transactions = list(
            (
                await session.execute(
                    select(CreditTransaction).where(CreditTransaction.user_id == user.id)
                )
            ).scalars()
        )

    assert persisted_user is not None
    assert persisted_user.credit_balance == 30
    assert [(tx.kind, tx.delta, tx.feature) for tx in transactions] == [
        ("consume", -20, "pipeline_run"),
    ]


@pytest.mark.asyncio
async def test_admin_user_bypasses_credit_debit(
    app,
    client,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
    get_settings.cache_clear()
    user, project = await create_user_and_project(
        session_factory,
        email="admin@example.com",
        credit_balance=0,
    )
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}

    class FakePipelineService:
        async def run_project(self, *, session, project) -> AgentState:
            return AgentState(
                project_id=project.id,
                topic=project.topic_description,
                queries=["admin bypass"],
                raw_papers=[],
                ranked_papers=[],
                summaries=[],
                qa_flags=[],
                errors=[],
            )

    app.dependency_overrides[get_pipeline_service] = lambda: FakePipelineService()
    response = await client.post(f"/projects/{project.id}/run", headers=headers)
    app.dependency_overrides.pop(get_pipeline_service, None)

    assert response.status_code == 200

    async with session_factory() as session:
        persisted_user = await session.get(User, user.id)
        transactions = list(
            (
                await session.execute(
                    select(CreditTransaction).where(CreditTransaction.user_id == user.id)
                )
            ).scalars()
        )

    assert persisted_user is not None
    assert persisted_user.credit_balance == 0
    assert transactions == []


@pytest.mark.asyncio
async def test_pipeline_route_refunds_debit_when_pipeline_raises(
    app,
    client,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user, project = await create_user_and_project(
        session_factory,
        email="quota-refund@example.com",
        credit_balance=50,
    )
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}

    class FailingPipelineService:
        async def run_project(self, *, session, project) -> AgentState:
            raise RuntimeError("pipeline exploded")

    app.dependency_overrides[get_pipeline_service] = lambda: FailingPipelineService()
    with pytest.raises(RuntimeError, match="pipeline exploded"):
        await client.post(f"/projects/{project.id}/run", headers=headers)
    app.dependency_overrides.pop(get_pipeline_service, None)

    async with session_factory() as session:
        persisted_user = await session.get(User, user.id)
        transactions = list(
            (
                await session.execute(
                    select(CreditTransaction).where(CreditTransaction.user_id == user.id)
                )
            ).scalars()
        )

    assert persisted_user is not None
    assert persisted_user.credit_balance == 50
    assert {(tx.kind, tx.delta, tx.feature) for tx in transactions} == {
        ("consume", -20, "pipeline_run"),
        ("refund", 20, "pipeline_run"),
    }


@pytest.mark.asyncio
async def test_deep_search_stream_refunds_debit_when_service_emits_error(
    app,
    client,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user, project = await create_user_and_project(
        session_factory,
        email="deep-search-refund@example.com",
        credit_balance=100,
    )
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}

    class FailingDeepSearchService:
        async def stream_run(self, *, session, project, question, selected_papers):
            yield DeepSearchStreamEvent("error", {"detail": "deep search exploded"})

    app.dependency_overrides[get_deep_search_service] = lambda: FailingDeepSearchService()
    response = await client.post(
        f"/projects/{project.id}/deep-search/stream",
        headers=headers,
        json={"question": "Why did this fail?", "paper_ids": []},
    )
    app.dependency_overrides.pop(get_deep_search_service, None)

    assert response.status_code == 201
    assert "event: error" in response.text
    assert "deep search exploded" in response.text

    async with session_factory() as session:
        persisted_user = await session.get(User, user.id)
        transactions = list(
            (
                await session.execute(
                    select(CreditTransaction).where(CreditTransaction.user_id == user.id)
                )
            ).scalars()
        )

    assert persisted_user is not None
    assert persisted_user.credit_balance == 100
    assert {(tx.kind, tx.delta, tx.feature) for tx in transactions} == {
        ("consume", -80, "deep_search"),
        ("refund", 80, "deep_search"),
    }
