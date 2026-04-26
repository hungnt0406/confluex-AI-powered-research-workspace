import asyncio
import json

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.api.dependencies import get_project_conversation_service
from backend.db.models import (
    AIUsageEvent,
    Paper,
    PaperChunk,
    ProjectConversation,
    ProjectMessage,
    Summary,
    User,
)
from backend.security import create_access_token, hash_password
from backend.services.project_conversations import (
    PROJECT_GROUNDING_UNAVAILABLE_MESSAGE,
    ProjectConversationService,
    ProjectConversationTurnContext,
)


class FakeEmbeddingService:
    def __init__(self, embeddings: list[list[float]]) -> None:
        self.embeddings = list(embeddings)

    async def embed_texts(self, texts: list[str], *, feature: str | None = None) -> list[list[float]]:
        assert len(texts) == 1
        assert self.embeddings
        return [self.embeddings.pop(0)]


def parse_sse_events(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for frame in body.strip().split("\n\n"):
        event_name = "message"
        data_lines: list[str] = []
        for line in frame.splitlines():
            if line.startswith("event:"):
                event_name = line.removeprefix("event:").strip()
            if line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").strip())
        if data_lines:
            events.append((event_name, json.loads("\n".join(data_lines))))
    return events


async def create_project_paper(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    project_id: str,
    title: str,
    doi: str,
    embedding: list[float],
) -> Paper:
    async with session_factory() as session:
        paper = Paper(
            project_id=project_id,
            title=title,
            authors=["Ada Lovelace"],
            year=2024,
            abstract=f"{title} abstract",
            doi=doi,
            source="semantic_scholar",
            source_paper_id=f"source-{doi}",
            source_url=f"https://papers.example.com/{doi}",
            pdf_url=f"https://papers.example.com/{doi}.pdf",
            status="summarized",
            relevance_score=90.0,
        )
        session.add(paper)
        await session.flush()
        session.add(
            Summary(
                paper_id=paper.id,
                problem=f"{title} problem",
                method=f"{title} method",
                result=f"{title} result",
                relevance_to_topic=f"{title} relevance",
                has_error=False,
                error_message=None,
            )
        )
        session.add(
            PaperChunk(
                paper_id=paper.id,
                chunk_index=0,
                page_start=1,
                page_end=2,
                section_title="Method",
                content=f"{title} explains its core method in detail.",
                embedding_json=embedding,
            )
        )
        await session.commit()
        await session.refresh(paper)
        return paper


async def create_auth_headers_for_email(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    email: str,
) -> dict[str, str]:
    async with session_factory() as session:
        user = User(email=email, hashed_password=hash_password("supersecret123"))
        session.add(user)
        await session.commit()
        await session.refresh(user)

    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_project_conversation_returns_grounded_multi_paper_answer(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_project: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    paper_one = await create_project_paper(
        session_factory,
        project_id=sample_project["id"],
        title="Paper One",
        doi="paper-one",
        embedding=[1.0, 0.0],
    )
    paper_two = await create_project_paper(
        session_factory,
        project_id=sample_project["id"],
        title="Paper Two",
        doi="paper-two",
        embedding=[0.8, 0.2],
    )

    service = ProjectConversationService(
        api_key="placeholder-key",
        embedding_service=FakeEmbeddingService([[1.0, 0.0]]),
    )
    app.dependency_overrides[get_project_conversation_service] = lambda: service

    response = await client.post(
        f"/projects/{sample_project['id']}/conversations",
        headers=auth_headers,
        json={
            "paper_ids": [paper_one.id, paper_two.id],
            "question": "Compare the selected methods.",
        },
    )
    app.dependency_overrides.pop(get_project_conversation_service, None)

    assert response.status_code == 201
    payload = response.json()
    assert payload["project_id"] == sample_project["id"]
    assert payload["selected_paper_ids"] == [paper_one.id, paper_two.id]
    assert payload["messages"][0]["role"] == "user"
    assert payload["messages"][1]["role"] == "assistant"
    assert "Paper One" in payload["messages"][1]["content"]
    assert "Paper Two" in payload["messages"][1]["content"]
    assert response.headers["Location"].endswith(f"/conversations/{payload['id']}")


@pytest.mark.asyncio
async def test_create_project_conversation_allows_no_selected_papers(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_project: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    paper = await create_project_paper(
        session_factory,
        project_id=sample_project["id"],
        title="Top Ranked Paper",
        doi="top-ranked-paper",
        embedding=[1.0, 0.0],
    )

    service = ProjectConversationService(
        api_key="placeholder-key",
        embedding_service=FakeEmbeddingService([]),
    )
    app.dependency_overrides[get_project_conversation_service] = lambda: service

    response = await client.post(
        f"/projects/{sample_project['id']}/conversations",
        headers=auth_headers,
        json={
            "paper_ids": [],
            "question": "What is a distributed system?",
        },
    )
    app.dependency_overrides.pop(get_project_conversation_service, None)

    assert response.status_code == 201
    payload = response.json()
    assert payload["selected_paper_ids"] == []
    assert payload["messages"][0]["content"] == "What is a distributed system?"
    assert "No papers are selected yet" in payload["messages"][1]["content"]
    assert paper.title not in payload["messages"][1]["content"]


@pytest.mark.asyncio
async def test_stream_create_project_conversation_emits_events_and_persists_messages(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_project: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    paper = await create_project_paper(
        session_factory,
        project_id=sample_project["id"],
        title="Streaming Paper",
        doi="streaming-paper",
        embedding=[1.0, 0.0],
    )
    service = ProjectConversationService(
        api_key="placeholder-key",
        embedding_service=FakeEmbeddingService([[1.0, 0.0]]),
    )
    app.dependency_overrides[get_project_conversation_service] = lambda: service

    response = await client.post(
        f"/projects/{sample_project['id']}/conversations/stream",
        headers=auth_headers,
        json={"paper_ids": [paper.id], "question": "Stream this answer."},
    )
    app.dependency_overrides.pop(get_project_conversation_service, None)

    assert response.status_code == 201
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    events = parse_sse_events(response.text)
    event_names = [event_name for event_name, _ in events]
    assert event_names[:3] == ["conversation", "status", "status"]
    assert "token" in event_names
    assert event_names[-1] == "done"
    assert events[1][1] == {"phase": "retrieving"}
    assert events[2][1] == {"phase": "generating"}
    done_payload = events[-1][1]
    assert done_payload["project_id"] == sample_project["id"]
    assert [message["role"] for message in done_payload["messages"]] == ["user", "assistant"]
    assert "Streaming Paper" in done_payload["messages"][1]["content"]

    async with session_factory() as session:
        result = await session.execute(
            select(ProjectMessage).where(ProjectMessage.conversation_id == done_payload["id"])
        )
        assert [message.role for message in result.scalars().all()] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_project_conversation_follow_up_inserts_system_message_when_selection_changes(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_project: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    paper_one = await create_project_paper(
        session_factory,
        project_id=sample_project["id"],
        title="Paper One",
        doi="paper-one",
        embedding=[1.0, 0.0],
    )
    paper_two = await create_project_paper(
        session_factory,
        project_id=sample_project["id"],
        title="Paper Two",
        doi="paper-two",
        embedding=[0.0, 1.0],
    )

    service = ProjectConversationService(
        api_key="placeholder-key",
        embedding_service=FakeEmbeddingService([[1.0, 0.0], [0.0, 1.0]]),
    )
    app.dependency_overrides[get_project_conversation_service] = lambda: service

    create_response = await client.post(
        f"/projects/{sample_project['id']}/conversations",
        headers=auth_headers,
        json={
            "paper_ids": [paper_one.id],
            "question": "Summarize the first paper.",
        },
    )
    conversation_id = create_response.json()["id"]

    follow_up_response = await client.post(
        f"/projects/{sample_project['id']}/conversations/{conversation_id}/messages",
        headers=auth_headers,
        json={
            "paper_ids": [paper_one.id, paper_two.id],
            "question": "Now compare both papers.",
        },
    )
    app.dependency_overrides.pop(get_project_conversation_service, None)

    assert follow_up_response.status_code == 200
    payload = follow_up_response.json()
    assert payload["selected_paper_ids"] == [paper_one.id, paper_two.id]
    assert [message["role"] for message in payload["messages"]] == [
        "user",
        "assistant",
        "system",
        "user",
        "assistant",
    ]
    assert "Selected papers updated:" in payload["messages"][2]["content"]

    async with session_factory() as session:
        conversation = await session.get(ProjectConversation, conversation_id)
        assert conversation is not None
        assert conversation.selected_paper_ids_json == [paper_one.id, paper_two.id]


@pytest.mark.asyncio
async def test_stream_follow_up_preserves_selection_change_system_message(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_project: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    paper_one = await create_project_paper(
        session_factory,
        project_id=sample_project["id"],
        title="Paper One",
        doi="stream-paper-one",
        embedding=[1.0, 0.0],
    )
    paper_two = await create_project_paper(
        session_factory,
        project_id=sample_project["id"],
        title="Paper Two",
        doi="stream-paper-two",
        embedding=[0.0, 1.0],
    )
    service = ProjectConversationService(
        api_key="placeholder-key",
        embedding_service=FakeEmbeddingService([[1.0, 0.0], [0.0, 1.0]]),
    )
    app.dependency_overrides[get_project_conversation_service] = lambda: service
    create_response = await client.post(
        f"/projects/{sample_project['id']}/conversations",
        headers=auth_headers,
        json={"paper_ids": [paper_one.id], "question": "Summarize the first paper."},
    )
    conversation_id = create_response.json()["id"]

    follow_up_response = await client.post(
        f"/projects/{sample_project['id']}/conversations/{conversation_id}/messages/stream",
        headers=auth_headers,
        json={
            "paper_ids": [paper_one.id, paper_two.id],
            "question": "Now compare both papers.",
        },
    )
    app.dependency_overrides.pop(get_project_conversation_service, None)

    assert follow_up_response.status_code == 200
    events = parse_sse_events(follow_up_response.text)
    done_payload = events[-1][1]
    assert [message["role"] for message in done_payload["messages"]] == [
        "user",
        "assistant",
        "system",
        "user",
        "assistant",
    ]
    assert "Selected papers updated:" in done_payload["messages"][2]["content"]


@pytest.mark.asyncio
async def test_openrouter_streaming_chunks_are_sanitized_persisted_and_usage_flushed(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_project: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    paper = await create_project_paper(
        session_factory,
        project_id=sample_project["id"],
        title="Live Stream Paper",
        doi="live-stream-paper",
        embedding=[1.0, 0.0],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["stream"] is True
        assert payload["stream_options"] == {"include_usage": True}
        assert payload["messages"][1]["content"].startswith("Question: What does it show?")
        body = "\n\n".join(
            [
                'data: {"choices":[{"delta":{"content":"The answer uses [Chunk 1] pages 1-2, "}}]}',
                'data: {"choices":[{"delta":{"content":"score=0.99 retrieved evidence."}}]}',
                'data: {"choices":[],"usage":{"prompt_tokens":11,"completion_tokens":7,"total_tokens":18,"cost":0.001}}',
                "data: [DONE]",
                "",
            ]
        )
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as openrouter_client:
        service = ProjectConversationService(
            api_key="sk-live-test",
            http_client=openrouter_client,
            embedding_service=FakeEmbeddingService([[1.0, 0.0]]),
        )
        app.dependency_overrides[get_project_conversation_service] = lambda: service
        response = await client.post(
            f"/projects/{sample_project['id']}/conversations/stream",
            headers=auth_headers,
            json={"paper_ids": [paper.id], "question": "What does it show?"},
        )
        app.dependency_overrides.pop(get_project_conversation_service, None)

    assert response.status_code == 201
    events = parse_sse_events(response.text)
    token_text = "".join(data["delta"] for event_name, data in events if event_name == "token")
    assert "The answer uses" in token_text
    done_payload = events[-1][1]
    assistant_content = done_payload["messages"][1]["content"]
    assert "retrieved evidence" in assistant_content
    assert "Chunk" not in assistant_content
    assert "Similarity" not in assistant_content

    async with session_factory() as session:
        usage_result = await session.execute(
            select(AIUsageEvent).where(AIUsageEvent.project_id == sample_project["id"])
        )
        usage_events = usage_result.scalars().all()
        assert len(usage_events) == 1
        assert usage_events[0].feature == "project_chat_answer"
        assert usage_events[0].total_tokens == 18


@pytest.mark.asyncio
async def test_openrouter_midstream_error_emits_error_without_partial_assistant_persist(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_project: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    paper = await create_project_paper(
        session_factory,
        project_id=sample_project["id"],
        title="Error Stream Paper",
        doi="error-stream-paper",
        embedding=[1.0, 0.0],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        body = "\n\n".join(
            [
                'data: {"choices":[{"delta":{"content":"partial answer"}}]}',
                'data: {"error":{"message":"provider failed mid-stream"}}',
                "",
            ]
        )
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as openrouter_client:
        service = ProjectConversationService(
            api_key="sk-live-test",
            http_client=openrouter_client,
            embedding_service=FakeEmbeddingService([[1.0, 0.0]]),
        )
        app.dependency_overrides[get_project_conversation_service] = lambda: service
        response = await client.post(
            f"/projects/{sample_project['id']}/conversations/stream",
            headers=auth_headers,
            json={"paper_ids": [paper.id], "question": "Trigger provider failure."},
        )
        app.dependency_overrides.pop(get_project_conversation_service, None)

    assert response.status_code == 201
    events = parse_sse_events(response.text)
    assert [event_name for event_name, _ in events][-1] == "error"
    assert events[-1][1] == {"detail": "provider failed mid-stream"}

    async with session_factory() as session:
        message_result = await session.execute(
            select(ProjectMessage).where(ProjectMessage.content == "partial answer")
        )
        assert message_result.scalars().all() == []


@pytest.mark.asyncio
async def test_stream_answer_falls_back_when_provider_sends_no_first_token() -> None:
    service = ProjectConversationService(api_key="sk-live-test")
    service.timeout_seconds = 0.01

    async def hanging_live_answer(**_: object):
        await asyncio.sleep(1)
        yield "unreachable"

    service._stream_live_answer = hanging_live_answer  # type: ignore[method-assign]
    conversation = ProjectConversation(project_id="project-1", selected_paper_ids_json=[])
    turn_context = ProjectConversationTurnContext(
        conversation=conversation,
        selected_papers=[],
        question="What is streaming?",
        recent_messages=[],
        retrieved_chunks=[],
        extraction_errors=[],
        used_metadata_fallback=True,
        touch_updated_at=False,
    )

    tokens = [token async for token in service._stream_answer(turn_context)]

    assert len(tokens) == 1
    assert "No papers are selected yet" in tokens[0]


@pytest.mark.asyncio
async def test_project_conversation_rejects_missing_selected_paper(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_project: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    paper = await create_project_paper(
        session_factory,
        project_id=sample_project["id"],
        title="Paper One",
        doi="paper-one",
        embedding=[1.0, 0.0],
    )

    service = ProjectConversationService(
        api_key="placeholder-key",
        embedding_service=FakeEmbeddingService([[1.0, 0.0]]),
    )
    app.dependency_overrides[get_project_conversation_service] = lambda: service

    response = await client.post(
        f"/projects/{sample_project['id']}/conversations",
        headers=auth_headers,
        json={
            "paper_ids": [paper.id, "missing-paper"],
            "question": "Compare these papers.",
        },
    )
    app.dependency_overrides.pop(get_project_conversation_service, None)

    assert response.status_code == 404
    assert response.json() == {"detail": "One or more selected papers were not found in the project."}

    stream_response = await client.post(
        f"/projects/{sample_project['id']}/conversations/stream",
        headers=auth_headers,
        json={
            "paper_ids": [paper.id, "missing-paper"],
            "question": "Compare these papers.",
        },
    )
    assert stream_response.status_code == 404
    assert stream_response.json() == {
        "detail": "One or more selected papers were not found in the project."
    }


@pytest.mark.asyncio
async def test_list_and_get_project_conversations_enforce_ownership(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_project: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    paper = await create_project_paper(
        session_factory,
        project_id=sample_project["id"],
        title="Paper One",
        doi="paper-one",
        embedding=[1.0, 0.0],
    )
    service = ProjectConversationService(
        api_key="placeholder-key",
        embedding_service=FakeEmbeddingService([[1.0, 0.0]]),
    )
    app.dependency_overrides[get_project_conversation_service] = lambda: service
    create_response = await client.post(
        f"/projects/{sample_project['id']}/conversations",
        headers=auth_headers,
        json={"paper_ids": [paper.id], "question": "Summarize this paper."},
    )
    app.dependency_overrides.pop(get_project_conversation_service, None)
    conversation_id = create_response.json()["id"]

    list_response = await client.get(
        f"/projects/{sample_project['id']}/conversations",
        headers=auth_headers,
    )
    detail_response = await client.get(
        f"/projects/{sample_project['id']}/conversations/{conversation_id}",
        headers=auth_headers,
    )
    other_headers = await create_auth_headers_for_email(
        session_factory,
        email="intruder@example.com",
    )
    unauthorized_response = await client.get(
        f"/projects/{sample_project['id']}/conversations",
        headers=other_headers,
    )

    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["selected_paper_ids"] == [paper.id]
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == conversation_id
    assert unauthorized_response.status_code == 404


@pytest.mark.asyncio
async def test_project_conversation_validates_unique_and_max_selected_papers(
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_project: dict[str, str],
) -> None:
    duplicate_response = await client.post(
        f"/projects/{sample_project['id']}/conversations",
        headers=auth_headers,
        json={"paper_ids": ["paper-1", "paper-1"], "question": "Duplicate ids."},
    )
    too_many_response = await client.post(
        f"/projects/{sample_project['id']}/conversations",
        headers=auth_headers,
        json={
            "paper_ids": ["p1", "p2", "p3", "p4", "p5", "p6"],
            "question": "Too many ids.",
        },
    )
    duplicate_stream_response = await client.post(
        f"/projects/{sample_project['id']}/conversations/stream",
        headers=auth_headers,
        json={"paper_ids": ["paper-1", "paper-1"], "question": "Duplicate ids."},
    )

    assert duplicate_response.status_code == 422
    assert too_many_response.status_code == 422
    assert duplicate_stream_response.status_code == 422


def test_project_prompt_and_answer_hide_raw_grounding_provider_errors() -> None:
    service = ProjectConversationService(api_key="placeholder-key")
    paper = Paper(
        project_id="project-1",
        title="TrackNet",
        authors=[],
        year=2024,
        abstract="TrackNet abstract.",
        doi=None,
        source="user_upload",
        source_paper_id="tracknet",
        source_url=None,
        pdf_url="data/reference_uploads/project-1/tracknet.pdf",
        status="candidate",
        relevance_score=None,
    )
    raw_error = (
        "TrackNet: OpenRouter PDF extraction with engine 'native' failed with status 400: "
        '{"error":{"message":"Invalid content","metadata":{"provider_name":"Google AI Studio"}}}; '
        "Public PDF download failed."
    )

    prompt = service._build_prompt(
        selected_papers=[paper],
        question="What architecture does it use?",
        recent_messages=[],
        retrieved_chunks=[],
        extraction_errors=[raw_error],
    )
    answer = service._generate_local_answer(
        selected_papers=[paper],
        question="What architecture does it use?",
        recent_messages=[],
        retrieved_chunks=[],
        extraction_errors=[raw_error],
    )

    assert raw_error not in prompt
    assert "OpenRouter PDF extraction" not in prompt
    assert "Public PDF download failed" not in prompt
    assert "No retrieved chunk grounding is available" not in prompt
    assert PROJECT_GROUNDING_UNAVAILABLE_MESSAGE in prompt
    assert "OpenRouter PDF extraction" not in answer
    assert "Public PDF download failed" not in answer
    assert "provider_name" not in answer
    assert PROJECT_GROUNDING_UNAVAILABLE_MESSAGE in answer
