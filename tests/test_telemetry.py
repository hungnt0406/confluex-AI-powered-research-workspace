import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.db.models import MessageFeedbackEvent


@pytest.mark.asyncio
async def test_record_message_feedback_persists_event(
    client,
    auth_headers,
    sample_user,
    sample_project,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    payload = {
        "action": "like",
        "surface": "chat",
        "message_id": "msg-123",
        "project_id": sample_project["id"],
        "content_preview": "The first wave of retrieval-augmented generation...",
        "metadata": {"length": 482},
    }

    response = await client.post(
        "/telemetry/message-feedback",
        headers=auth_headers,
        json=payload,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["action"] == "like"
    assert body["surface"] == "chat"
    assert body["project_id"] == sample_project["id"]
    assert body["message_id"] == "msg-123"

    async with session_factory() as session:
        rows = (await session.execute(select(MessageFeedbackEvent))).scalars().all()
        assert len(rows) == 1
        stored = rows[0]
        assert stored.user_id == sample_user["id"]
        assert stored.action == "like"
        assert stored.content_preview.startswith("The first wave")
        assert stored.metadata_json == {"length": 482}


@pytest.mark.asyncio
async def test_record_message_feedback_without_project(
    client,
    auth_headers,
) -> None:
    response = await client.post(
        "/telemetry/message-feedback",
        headers=auth_headers,
        json={"action": "copy", "surface": "chat"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["project_id"] is None
    assert body["action"] == "copy"


@pytest.mark.asyncio
async def test_record_message_feedback_rejects_unknown_project(
    client,
    auth_headers,
) -> None:
    response = await client.post(
        "/telemetry/message-feedback",
        headers=auth_headers,
        json={
            "action": "dislike",
            "surface": "chat",
            "project_id": "00000000-0000-0000-0000-000000000000",
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_record_message_feedback_requires_auth(client) -> None:
    response = await client.post(
        "/telemetry/message-feedback",
        json={"action": "like", "surface": "chat"},
    )
    assert response.status_code in (401, 403)
