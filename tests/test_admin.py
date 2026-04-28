from datetime import UTC, datetime

import pytest

from backend.config import get_settings
from backend.db.models import AIUsageEvent, Project, User
from backend.security import create_access_token, hash_password


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _auth_headers(user_id: str) -> dict[str, str]:
    token = create_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_admin_access_reports_allowlist_membership(
    client,
    auth_headers,
    sample_user,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ADMIN_EMAILS", f" {sample_user['email'].upper()} , owner@example.com ")
    get_settings.cache_clear()

    response = await client.get("/admin/access", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"is_admin": True}

    monkeypatch.setenv("ADMIN_EMAILS", "owner@example.com")
    get_settings.cache_clear()

    response = await client.get("/admin/access", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"is_admin": False}


@pytest.mark.asyncio
async def test_admin_token_usage_requires_admin_allowlist(
    client,
    auth_headers,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ADMIN_EMAILS", "owner@example.com")
    get_settings.cache_clear()

    response = await client.get("/admin/token-usage", headers=auth_headers)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_token_usage_aggregates_across_users_and_projects(
    client,
    auth_headers,
    sample_project,
    sample_user,
    session_factory,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ADMIN_EMAILS", sample_user["email"])
    get_settings.cache_clear()

    async with session_factory() as session:
        other_user = User(
            email="usage-team@example.com",
            hashed_password=hash_password("supersecret123"),
        )
        session.add(other_user)
        await session.flush()
        other_project = Project(
            user_id=other_user.id,
            title="Team Research",
            topic_description="Shared usage monitor fixture.",
            citation_format="APA",
            year_start=2020,
            candidate_limit=10,
            summary_limit=5,
        )
        session.add(other_project)
        await session.flush()
        session.add_all(
            [
                AIUsageEvent(
                    user_id=sample_user["id"],
                    project_id=sample_project["id"],
                    provider="openrouter",
                    endpoint="chat/completions",
                    feature="project_chat_answer",
                    model="model-a",
                    status="success",
                    prompt_tokens=20,
                    completion_tokens=10,
                    total_tokens=30,
                    reasoning_tokens=4,
                    cached_tokens=3,
                    cost_credits=0.03,
                    metadata_json={},
                    created_at=datetime(2026, 4, 20, 12, 0, tzinfo=UTC),
                ),
                AIUsageEvent(
                    user_id=other_user.id,
                    project_id=other_project.id,
                    provider="openrouter",
                    endpoint="chat/completions",
                    feature="paper_summary",
                    model="model-b",
                    status="success",
                    prompt_tokens=25,
                    completion_tokens=15,
                    total_tokens=40,
                    reasoning_tokens=None,
                    cached_tokens=2,
                    cost_credits=0.04,
                    metadata_json={},
                    created_at=datetime(2026, 4, 21, 12, 0, tzinfo=UTC),
                ),
            ]
        )
        await session.commit()

    response = await client.get(
        "/admin/token-usage?date_from=2026-04-01&date_to=2026-04-30",
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_tokens"] == 70
    assert payload["prompt_tokens"] == 45
    assert payload["completion_tokens"] == 25
    assert payload["reasoning_tokens"] == 4
    assert payload["cached_tokens"] == 5
    assert payload["request_count"] == 2
    assert payload["cost_credits"] == pytest.approx(0.07)
    assert {row["key"] for row in payload["by_feature"]} == {
        "paper_summary",
        "project_chat_answer",
    }
    assert {row["key"] for row in payload["by_model"]} == {"model-a", "model-b"}
    assert [row["day"] for row in payload["by_day"]] == ["2026-04-20", "2026-04-21"]
    assert {row["user_email"] for row in payload["by_user"]} == {
        sample_user["email"],
        "usage-team@example.com",
    }
    assert {row["project_title"] for row in payload["by_project"]} == {
        sample_project["title"],
        "Team Research",
    }
    assert [event["total_tokens"] for event in payload["recent_events"]] == [40, 30]
    assert payload["recent_events"][0]["user_email"] == "usage-team@example.com"
    assert payload["recent_events"][0]["project_title"] == "Team Research"


@pytest.mark.asyncio
async def test_admin_token_usage_filters_by_user_project_and_date(
    client,
    sample_project,
    sample_user,
    session_factory,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ADMIN_EMAILS", sample_user["email"])
    get_settings.cache_clear()

    async with session_factory() as session:
        other_user = User(
            email="filtered-owner@example.com",
            hashed_password=hash_password("supersecret123"),
        )
        session.add(other_user)
        await session.flush()
        other_project = Project(
            user_id=other_user.id,
            title="Filtered Project",
            topic_description="Usage filter fixture.",
            citation_format="APA",
            year_start=2020,
            candidate_limit=10,
            summary_limit=5,
        )
        session.add(other_project)
        await session.flush()
        session.add_all(
            [
                AIUsageEvent(
                    user_id=sample_user["id"],
                    project_id=sample_project["id"],
                    provider="openrouter",
                    endpoint="embeddings",
                    feature="ranking_embedding",
                    model="model-a",
                    status="success",
                    prompt_tokens=5,
                    completion_tokens=0,
                    total_tokens=5,
                    metadata_json={},
                    created_at=datetime(2026, 3, 30, 12, 0, tzinfo=UTC),
                ),
                AIUsageEvent(
                    user_id=other_user.id,
                    project_id=other_project.id,
                    provider="openrouter",
                    endpoint="chat/completions",
                    feature="paper_summary",
                    model="model-b",
                    status="success",
                    prompt_tokens=11,
                    completion_tokens=7,
                    total_tokens=18,
                    cost_credits=0.018,
                    metadata_json={},
                    created_at=datetime(2026, 4, 10, 12, 0, tzinfo=UTC),
                ),
                AIUsageEvent(
                    user_id=other_user.id,
                    project_id=other_project.id,
                    provider="openrouter",
                    endpoint="chat/completions",
                    feature="project_chat_answer",
                    model="model-c",
                    status="success",
                    prompt_tokens=13,
                    completion_tokens=9,
                    total_tokens=22,
                    cost_credits=0.022,
                    metadata_json={},
                    created_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
                ),
            ]
        )
        await session.commit()
        other_user_id = other_user.id
        other_project_id = other_project.id

    response = await client.get(
        (
            "/admin/token-usage"
            "?date_from=2026-04-01"
            "&date_to=2026-04-30"
            f"&user_id={other_user_id}"
            f"&project_id={other_project_id}"
        ),
        headers=_auth_headers(sample_user["id"]),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_tokens"] == 18
    assert payload["request_count"] == 1
    assert payload["cost_credits"] == pytest.approx(0.018)
    assert payload["by_user"] == [
        {
            "user_id": other_user_id,
            "user_email": "filtered-owner@example.com",
            "total_tokens": 18,
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "cost_credits": 0.018,
            "request_count": 1,
        }
    ]
    assert payload["by_project"][0]["project_id"] == other_project_id
    assert payload["recent_events"][0]["feature"] == "paper_summary"
