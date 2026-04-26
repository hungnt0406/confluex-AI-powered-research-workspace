import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.api.dependencies import get_project_conversation_service
from backend.db.models import Paper, PaperChunk, ProjectConversation, Summary, User
from backend.security import create_access_token, hash_password
from backend.services.project_conversations import ProjectConversationService


class FakeEmbeddingService:
    def __init__(self, embeddings: list[list[float]]) -> None:
        self.embeddings = list(embeddings)

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        assert len(texts) == 1
        assert self.embeddings
        return [self.embeddings.pop(0)]


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

    assert duplicate_response.status_code == 422
    assert too_many_response.status_code == 422
