import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.api.dependencies import get_paper_conversation_service
from backend.db.models import (
    Paper,
    PaperChunk,
    PaperConversation,
    PaperDocument,
    PaperMessage,
    Summary,
)
from backend.services.document_extraction import DocumentExtractionError
from backend.services.paper_conversations import PaperConversationService


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
    pdf_url: str | None = "https://papers.example.com/paper.pdf",
) -> Paper:
    async with session_factory() as session:
        paper = Paper(
            project_id=project_id,
            title="Grounded Paper Conversations",
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
