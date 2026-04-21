import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from backend.api.dependencies import get_paper_conversation_service
from backend.db.models import (
    Paper,
    PaperChunk,
    PaperConversation,
    PaperDocument,
    PaperMessage,
    Summary,
    User,
)
from backend.security import create_access_token, hash_password
from backend.services.document_extraction import DocumentExtractionError
from backend.services.paper_conversations import LIVE_ANSWER_SYSTEM_PROMPT, PaperConversationService


class FakeEmbeddingService:
    """Embedding stub that returns deterministic vectors for ranking tests."""

    def __init__(self, embeddings: list[list[float]]) -> None:
        self.embeddings = embeddings

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        assert len(texts) == len(self.embeddings)
        return self.embeddings


class RecordingExtractionService:
    """Extraction stub that inserts grounding rows on demand."""

    def __init__(self, *, chunk_text: str) -> None:
        self.chunk_text = chunk_text
        self.calls = 0

    async def ensure_document_chunks(self, *, session: AsyncSession, paper: Paper) -> PaperDocument:
        self.calls += 1
        document = PaperDocument(
            paper_id=paper.id,
            status="ready",
            source_pdf_url=paper.pdf_url or "https://papers.example.com/generated.pdf",
            openrouter_file_hash=f"hash-{paper.id}",
            page_count=1,
            error_message=None,
        )
        session.add(document)
        session.add(
            PaperChunk(
                paper_id=paper.id,
                chunk_index=0,
                page_start=1,
                page_end=1,
                section_title="Generated",
                content=self.chunk_text,
                embedding_json=[1.0, 0.0],
            )
        )
        await session.flush()
        return document


class FailingExtractionService:
    """Extraction stub that simulates failed grounding."""

    def __init__(self, message: str) -> None:
        self.message = message
        self.calls = 0

    async def ensure_document_chunks(self, *, session: AsyncSession, paper: Paper) -> object:
        self.calls += 1
        raise DocumentExtractionError(self.message)


async def create_sample_paper(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    project_id: str,
    title: str = "Grounded Paper Conversations",
    pdf_url: str | None = "https://papers.example.com/paper.pdf",
) -> Paper:
    async with session_factory() as session:
        paper = Paper(
            project_id=project_id,
            title=title,
            authors=["Ada Lovelace", "Grace Hopper"],
            year=2024,
            abstract="This paper studies grounded Q&A over scientific PDFs.",
            doi="10.1000/grounded-paper",
            source="semantic_scholar",
            source_paper_id="paper-source-1",
            source_url="https://papers.example.com/landing",
            pdf_url=pdf_url,
            status="summarized",
            relevance_score=92.0,
        )
        session.add(paper)
        await session.flush()
        session.add(
            Summary(
                paper_id=paper.id,
                problem="Users need grounded paper conversations.",
                method="Persist chunks and retrieve them per question.",
                result="Chunk-grounded answers are more specific than abstract-only responses.",
                relevance_to_topic="Directly relevant to paper understanding flows.",
                has_error=False,
                error_message=None,
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
async def test_create_paper_conversation_returns_first_turn_with_retrieved_chunk(
    app,
    client,
    auth_headers,
    sample_project,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    paper = await create_sample_paper(session_factory, project_id=sample_project["id"])
    async with session_factory() as session:
        session.add(
            PaperChunk(
                paper_id=paper.id,
                chunk_index=0,
                page_start=2,
                page_end=3,
                section_title="Method",
                content="This chunk explains the retrieval-first grounding method in detail.",
                embedding_json=[1.0, 0.0],
            )
        )
        session.add(
            PaperChunk(
                paper_id=paper.id,
                chunk_index=1,
                page_start=4,
                page_end=4,
                section_title="Ablation",
                content="This chunk is less relevant to the user question.",
                embedding_json=[0.0, 1.0],
            )
        )
        await session.commit()

    service = PaperConversationService(
        api_key="placeholder-key",
        retrieval_top_k=1,
        embedding_service=FakeEmbeddingService([[1.0, 0.0]]),
    )
    app.dependency_overrides[get_paper_conversation_service] = lambda: service

    response = await client.post(
        f"/projects/{sample_project['id']}/papers/{paper.id}/conversations",
        headers=auth_headers,
        json={"question": "How does the method ground answers?"},
    )
    app.dependency_overrides.pop(get_paper_conversation_service, None)

    assert response.status_code == 201
    payload = response.json()
    assert payload["paper_id"] == paper.id
    assert len(payload["messages"]) == 2
    assert payload["messages"][0]["role"] == "user"
    assert payload["messages"][0]["content"] == "How does the method ground answers?"
    assert payload["messages"][1]["role"] == "assistant"
    assert "retrieval-first grounding method" in payload["messages"][1]["content"]
    assert response.headers["Location"].endswith(f"/conversations/{payload['id']}")

    async with session_factory() as session:
        conversation_total = int((await session.execute(select(func.count()).select_from(PaperConversation))).scalar_one())
        message_total = int((await session.execute(select(func.count()).select_from(PaperMessage))).scalar_one())

    assert conversation_total == 1
    assert message_total == 2


@pytest.mark.asyncio
async def test_create_paper_conversation_extracts_chunks_when_missing(
    app,
    client,
    auth_headers,
    sample_project,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    paper = await create_sample_paper(session_factory, project_id=sample_project["id"])
    extraction_service = RecordingExtractionService(
        chunk_text="Generated chunk content about PDF extraction and retrieval."
    )
    service = PaperConversationService(
        api_key="placeholder-key",
        retrieval_top_k=1,
        extraction_service=extraction_service,
        embedding_service=FakeEmbeddingService([[1.0, 0.0]]),
    )
    app.dependency_overrides[get_paper_conversation_service] = lambda: service

    response = await client.post(
        f"/projects/{sample_project['id']}/papers/{paper.id}/conversations",
        headers=auth_headers,
        json={"question": "What was extracted from the PDF?"},
    )
    app.dependency_overrides.pop(get_paper_conversation_service, None)

    assert response.status_code == 201
    payload = response.json()
    assert extraction_service.calls == 1
    assert "Generated chunk content about PDF extraction" in payload["messages"][1]["content"]

    async with session_factory() as session:
        stored_chunks = list(
            (
                await session.execute(
                    select(PaperChunk)
                    .where(PaperChunk.paper_id == paper.id)
                    .order_by(PaperChunk.chunk_index.asc())
                )
            ).scalars()
        )

    assert len(stored_chunks) == 1


@pytest.mark.asyncio
async def test_create_paper_conversation_falls_back_to_metadata_when_extraction_fails(
    app,
    client,
    auth_headers,
    sample_project,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    paper = await create_sample_paper(session_factory, project_id=sample_project["id"])
    extraction_service = FailingExtractionService("Simulated extraction failure.")
    service = PaperConversationService(
        api_key="placeholder-key",
        extraction_service=extraction_service,
        embedding_service=FakeEmbeddingService([[1.0, 0.0]]),
    )
    app.dependency_overrides[get_paper_conversation_service] = lambda: service

    response = await client.post(
        f"/projects/{sample_project['id']}/papers/{paper.id}/conversations",
        headers=auth_headers,
        json={"question": "Summarize the paper for me."},
    )
    app.dependency_overrides.pop(get_paper_conversation_service, None)

    assert response.status_code == 201
    payload = response.json()
    assistant_message = payload["messages"][1]["content"]
    assert extraction_service.calls == 1
    assert "limited to the stored paper metadata" in assistant_message
    assert "Simulated extraction failure." in assistant_message
    assert "Persist chunks and retrieve them per question." in assistant_message


@pytest.mark.asyncio
async def test_create_paper_conversation_returns_404_for_unknown_paper(
    client,
    auth_headers,
    sample_project,
) -> None:
    response = await client.post(
        f"/projects/{sample_project['id']}/papers/missing-paper/conversations",
        headers=auth_headers,
        json={"question": "Does this paper exist?"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Paper not found."}


@pytest.mark.asyncio
async def test_create_paper_conversation_message_persists_follow_up_turn(
    app,
    client,
    auth_headers,
    sample_project,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    paper = await create_sample_paper(session_factory, project_id=sample_project["id"])
    async with session_factory() as session:
        session.add(
            PaperChunk(
                paper_id=paper.id,
                chunk_index=0,
                page_start=2,
                page_end=3,
                section_title="Method",
                content="This chunk explains the retrieval-first grounding method in detail.",
                embedding_json=[1.0, 0.0],
            )
        )
        await session.commit()

    service = PaperConversationService(
        api_key="placeholder-key",
        retrieval_top_k=1,
        embedding_service=FakeEmbeddingService([[1.0, 0.0]]),
    )
    app.dependency_overrides[get_paper_conversation_service] = lambda: service

    create_response = await client.post(
        f"/projects/{sample_project['id']}/papers/{paper.id}/conversations",
        headers=auth_headers,
        json={"question": "What does the method do?"},
    )
    assert create_response.status_code == 201
    create_payload = create_response.json()

    follow_up_response = await client.post(
        (
            f"/projects/{sample_project['id']}/papers/{paper.id}/conversations/"
            f"{create_payload['id']}/messages"
        ),
        headers=auth_headers,
        json={"question": "How is the answer grounded across turns?"},
    )
    app.dependency_overrides.pop(get_paper_conversation_service, None)

    assert follow_up_response.status_code == 200
    follow_up_payload = follow_up_response.json()
    assert len(follow_up_payload["messages"]) == 4
    assert follow_up_payload["messages"][-2]["role"] == "user"
    assert follow_up_payload["messages"][-2]["content"] == "How is the answer grounded across turns?"
    assert follow_up_payload["messages"][-1]["role"] == "assistant"
    assert "Recent conversation context:" in follow_up_payload["messages"][-1]["content"]
    assert "retrieval-first grounding method" in follow_up_payload["messages"][-1]["content"]
    assert follow_up_payload["updated_at"] != create_payload["updated_at"]

    async with session_factory() as session:
        message_total = int(
            (await session.execute(select(func.count()).select_from(PaperMessage))).scalar_one()
        )

    assert message_total == 4


@pytest.mark.asyncio
async def test_build_prompt_and_system_prompt_force_question_focused_answers(
    session_factory: async_sessionmaker[AsyncSession],
    sample_project,
) -> None:
    created_paper = await create_sample_paper(session_factory, project_id=sample_project["id"])
    async with session_factory() as session:
        paper = (
            await session.execute(
                select(Paper)
                .options(selectinload(Paper.summary))
                .where(Paper.id == created_paper.id)
            )
        ).scalar_one()
    service = PaperConversationService(
        api_key="placeholder-key",
        embedding_service=FakeEmbeddingService([[1.0, 0.0]]),
    )

    prompt = service._build_prompt(
        paper=paper,
        question="What is heatmap-based detection?",
        recent_messages=[
            PaperMessage(
                conversation_id="conversation-1",
                role="assistant",
                content="Previous answer about the broader method.",
            )
        ],
        retrieved_chunks=[],
        extraction_error=None,
    )

    assert "Answering rules:" in prompt
    assert "- Answer the current question directly." in prompt
    assert "- Do not switch into a generic paper summary unless the question asks for one." in prompt
    assert "Use recent conversation history only to resolve references from the current question." in prompt
    assert "When citing evidence, mention page numbers only and never mention chunk labels or similarity scores." in prompt
    assert "Pages:" not in prompt or "Retrieved paper excerpts:" in prompt
    assert "[Chunk" not in prompt
    assert "score=" not in prompt
    assert "Answer the user's current question directly instead of drifting into a generic paper summary." in LIVE_ANSWER_SYSTEM_PROMPT
    assert "Never mention internal retrieval labels like chunk numbers or similarity scores." in LIVE_ANSWER_SYSTEM_PROMPT


def test_sanitize_user_visible_text_removes_internal_chunk_labels() -> None:
    service = PaperConversationService(api_key="placeholder-key")

    sanitized = service._sanitize_user_visible_text(
        "Evidence: (Chunk 2, pages 4-4) text here. [Chunk 1] pages 6-6, score=0.981"
    )

    assert "Chunk 2" not in sanitized
    assert "Chunk 1" not in sanitized
    assert "score=0.981" not in sanitized
    assert "(pages 4-4)" in sanitized
    assert "pages 6-6" in sanitized


@pytest.mark.asyncio
async def test_list_paper_conversations_returns_summaries_in_latest_activity_order(
    app,
    client,
    auth_headers,
    sample_project,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    paper = await create_sample_paper(session_factory, project_id=sample_project["id"])
    async with session_factory() as session:
        session.add(
            PaperChunk(
                paper_id=paper.id,
                chunk_index=0,
                page_start=1,
                page_end=2,
                section_title="Method",
                content="This chunk explains how grounding persists across the conversation.",
                embedding_json=[1.0, 0.0],
            )
        )
        await session.commit()

    service = PaperConversationService(
        api_key="placeholder-key",
        retrieval_top_k=1,
        embedding_service=FakeEmbeddingService([[1.0, 0.0]]),
    )
    app.dependency_overrides[get_paper_conversation_service] = lambda: service

    first_response = await client.post(
        f"/projects/{sample_project['id']}/papers/{paper.id}/conversations",
        headers=auth_headers,
        json={"question": "Explain the method."},
    )
    assert first_response.status_code == 201
    first_payload = first_response.json()

    second_response = await client.post(
        f"/projects/{sample_project['id']}/papers/{paper.id}/conversations",
        headers=auth_headers,
        json={"question": "Summarize the paper."},
    )
    assert second_response.status_code == 201
    second_payload = second_response.json()

    follow_up_response = await client.post(
        (
            f"/projects/{sample_project['id']}/papers/{paper.id}/conversations/"
            f"{first_payload['id']}/messages"
        ),
        headers=auth_headers,
        json={"question": "What happens on later turns?"},
    )
    app.dependency_overrides.pop(get_paper_conversation_service, None)
    assert follow_up_response.status_code == 200

    list_response = await client.get(
        f"/projects/{sample_project['id']}/papers/{paper.id}/conversations",
        headers=auth_headers,
    )

    assert list_response.status_code == 200
    payload = list_response.json()
    assert [item["id"] for item in payload] == [first_payload["id"], second_payload["id"]]
    assert payload[0]["message_count"] == 4
    assert payload[0]["opening_question"] == "Explain the method."
    assert payload[1]["message_count"] == 2
    assert payload[1]["opening_question"] == "Summarize the paper."


@pytest.mark.asyncio
async def test_get_paper_conversation_returns_detail(
    app,
    client,
    auth_headers,
    sample_project,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    paper = await create_sample_paper(session_factory, project_id=sample_project["id"])
    async with session_factory() as session:
        session.add(
            PaperChunk(
                paper_id=paper.id,
                chunk_index=0,
                page_start=5,
                page_end=6,
                section_title="Evaluation",
                content="This chunk covers evaluation details for the grounded answers.",
                embedding_json=[1.0, 0.0],
            )
        )
        await session.commit()

    service = PaperConversationService(
        api_key="placeholder-key",
        retrieval_top_k=1,
        embedding_service=FakeEmbeddingService([[1.0, 0.0]]),
    )
    app.dependency_overrides[get_paper_conversation_service] = lambda: service

    create_response = await client.post(
        f"/projects/{sample_project['id']}/papers/{paper.id}/conversations",
        headers=auth_headers,
        json={"question": "What is evaluated?"},
    )
    app.dependency_overrides.pop(get_paper_conversation_service, None)
    assert create_response.status_code == 201
    create_payload = create_response.json()

    detail_response = await client.get(
        (
            f"/projects/{sample_project['id']}/papers/{paper.id}/conversations/"
            f"{create_payload['id']}"
        ),
        headers=auth_headers,
    )

    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["id"] == create_payload["id"]
    assert detail_payload["paper_id"] == paper.id
    assert len(detail_payload["messages"]) == 2
    assert detail_payload["messages"][0]["content"] == "What is evaluated?"


@pytest.mark.asyncio
async def test_create_paper_conversation_message_returns_404_for_mismatched_paper_and_conversation(
    app,
    client,
    auth_headers,
    sample_project,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    first_paper = await create_sample_paper(
        session_factory,
        project_id=sample_project["id"],
        title="First Paper",
    )
    second_paper = await create_sample_paper(
        session_factory,
        project_id=sample_project["id"],
        title="Second Paper",
    )
    async with session_factory() as session:
        session.add(
            PaperChunk(
                paper_id=first_paper.id,
                chunk_index=0,
                page_start=1,
                page_end=1,
                section_title="Intro",
                content="This chunk belongs to the first paper.",
                embedding_json=[1.0, 0.0],
            )
        )
        await session.commit()

    service = PaperConversationService(
        api_key="placeholder-key",
        retrieval_top_k=1,
        embedding_service=FakeEmbeddingService([[1.0, 0.0]]),
    )
    app.dependency_overrides[get_paper_conversation_service] = lambda: service

    create_response = await client.post(
        f"/projects/{sample_project['id']}/papers/{first_paper.id}/conversations",
        headers=auth_headers,
        json={"question": "Question for the first paper."},
    )
    app.dependency_overrides.pop(get_paper_conversation_service, None)
    assert create_response.status_code == 201
    create_payload = create_response.json()

    mismatch_response = await client.post(
        (
            f"/projects/{sample_project['id']}/papers/{second_paper.id}/conversations/"
            f"{create_payload['id']}/messages"
        ),
        headers=auth_headers,
        json={"question": "Try to continue under the wrong paper."},
    )

    assert mismatch_response.status_code == 404
    assert mismatch_response.json() == {"detail": "Conversation not found."}


@pytest.mark.asyncio
async def test_list_paper_conversations_returns_404_for_unowned_project(
    app,
    client,
    auth_headers,
    sample_project,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    paper = await create_sample_paper(session_factory, project_id=sample_project["id"])
    service = PaperConversationService(
        api_key="placeholder-key",
        retrieval_top_k=1,
        embedding_service=FakeEmbeddingService([[1.0, 0.0]]),
    )
    app.dependency_overrides[get_paper_conversation_service] = lambda: service

    create_response = await client.post(
        f"/projects/{sample_project['id']}/papers/{paper.id}/conversations",
        headers=auth_headers,
        json={"question": "Create a conversation before checking access."},
    )
    app.dependency_overrides.pop(get_paper_conversation_service, None)
    assert create_response.status_code == 201

    other_auth_headers = await create_auth_headers_for_email(
        session_factory,
        email="another-researcher@example.com",
    )
    response = await client.get(
        f"/projects/{sample_project['id']}/papers/{paper.id}/conversations",
        headers=other_auth_headers,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found."}
