import base64
import json
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.db.models import Paper, PaperChunk, PaperDocument, Project
from backend.services.document_extraction import (
    DocumentExtractionError,
    DocumentTextBlock,
    ExtractedDocument,
    PaperDocumentExtractionService,
)


class FakeEmbeddingService:
    """Deterministic embedding stub for chunk-persistence tests."""

    async def embed_texts(self, texts: list[str], *, feature: str | None = None) -> list[list[float]]:
        return [
            [float(index), float(len(text)), float(len(text.split()))]
            for index, text in enumerate(texts, start=1)
        ]


def build_pdf_bytes(pages: list[str]) -> bytes:
    joined_pages = "\n\n".join(pages)
    return f"%PDF-1.4\n%mock\n{joined_pages}\n%%EOF".encode()


@pytest.mark.asyncio
@respx.mock
async def test_document_extraction_service_extracts_uploaded_pdf_via_openrouter_base64() -> None:
    pdf_bytes = build_pdf_bytes(["Uploaded PDF\n\nThis content is sent as a local PDF."])
    captured_request: dict[str, object] | None = None

    def openrouter_handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": "Acknowledged.",
                            "annotations": [
                                {
                                    "type": "file",
                                    "file": {
                                        "hash": "uploaded-file-hash",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": (
                                                    "LLM Extracted Uploaded Paper\n\n"
                                                    "Abstract\n\n"
                                                    "This paper was extracted from uploaded bytes."
                                                ),
                                            }
                                        ],
                                    },
                                }
                            ],
                        },
                    }
                ]
            },
        )

    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        side_effect=openrouter_handler
    )

    service = PaperDocumentExtractionService(
        api_key="sk-or-test-key",
        model="google/gemini-2.5-flash-lite",
    )
    document = await service.extract_uploaded_pdf(pdf_bytes=pdf_bytes, filename="seed.pdf")

    assert route.called
    assert captured_request is not None
    messages = captured_request["messages"]
    assert isinstance(messages, list)
    file_payload = messages[0]["content"][1]["file"]
    assert file_payload["filename"] == "seed.pdf"
    assert file_payload["file_data"].startswith("data:application/pdf;base64,")
    encoded_payload = file_payload["file_data"].split(",", maxsplit=1)[1]
    assert base64.b64decode(encoded_payload) == pdf_bytes
    assert captured_request["plugins"] == [{"id": "file-parser", "pdf": {"engine": "native"}}]
    assert document.file_hash == "uploaded-file-hash"
    assert document.page_count == 1
    assert document.blocks[0].text.startswith("LLM Extracted Uploaded Paper")


async def create_sample_paper(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    project_id: str,
    pdf_url: str,
) -> Paper:
    async with session_factory() as session:
        project = await session.get(Project, project_id)
        assert project is not None

        paper = Paper(
            project_id=project.id,
            title="Structured Paper Grounding",
            authors=["Ada Lovelace", "Grace Hopper"],
            year=2024,
            abstract="A sample paper for document extraction tests.",
            doi=None,
            source="semantic_scholar",
            source_paper_id="paper-123",
            source_url="https://papers.example.com/landing",
            pdf_url=pdf_url,
            status="summarized",
            relevance_score=0.91,
        )
        session.add(paper)
        await session.commit()
        await session.refresh(paper)
        return paper


async def load_document_and_chunks(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    paper_id: str,
) -> tuple[PaperDocument | None, list[PaperChunk]]:
    async with session_factory() as session:
        document = (
            await session.execute(select(PaperDocument).where(PaperDocument.paper_id == paper_id))
        ).scalar_one_or_none()
        chunks = list(
            (
                await session.execute(
                    select(PaperChunk)
                    .where(PaperChunk.paper_id == paper_id)
                    .order_by(PaperChunk.chunk_index)
                )
            ).scalars()
        )
        return document, chunks


@pytest.mark.asyncio
async def test_document_extraction_service_routes_local_pdf_paths_through_uploaded_pdf_extraction(
    session_factory: async_sessionmaker[AsyncSession],
    sample_project: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_bytes = build_pdf_bytes(
        ["Local Upload\n\nThis local PDF should be routed through uploaded PDF extraction."]
    )
    local_pdf_path = tmp_path / "uploaded-local.pdf"
    local_pdf_path.write_bytes(pdf_bytes)

    paper = await create_sample_paper(
        session_factory,
        project_id=sample_project["id"],
        pdf_url=str(local_pdf_path),
    )

    extracted_payloads: list[tuple[bytes, str]] = []

    async with session_factory() as session:
        persisted_paper = await session.get(Paper, paper.id)
        assert persisted_paper is not None

        service = PaperDocumentExtractionService(
            api_key="placeholder-key",
            local_pdf_roots=[tmp_path],
            embedding_service=FakeEmbeddingService(),
        )

        async def fake_extract_uploaded_pdf(*, pdf_bytes: bytes, filename: str) -> ExtractedDocument:
            extracted_payloads.append((pdf_bytes, filename))
            return ExtractedDocument(
                blocks=[
                    DocumentTextBlock(
                        page_number=1,
                        section_title="Local Upload",
                        text="This local PDF should be routed through uploaded PDF extraction.",
                    )
                ],
                page_count=1,
                file_hash=None,
            )

        async def fail_download(_: str) -> bytes:
            raise AssertionError("Local PDF paths should not use public HTTP download.")

        async def fail_openrouter(*, pdf_url: str, filename: str) -> ExtractedDocument:
            raise AssertionError(f"Local PDF path should not be sent to OpenRouter: {pdf_url}")

        monkeypatch.setattr(service, "extract_uploaded_pdf", fake_extract_uploaded_pdf)
        monkeypatch.setattr(service, "_download_pdf", fail_download)
        monkeypatch.setattr(service, "_extract_with_openrouter", fail_openrouter)

        await service.ensure_document_chunks(session=session, paper=persisted_paper)
        await session.commit()

    document, chunks = await load_document_and_chunks(session_factory, paper_id=paper.id)

    assert extracted_payloads == [(pdf_bytes, "uploaded-local.pdf")]
    assert document is not None
    assert document.status == "ready"
    assert document.source_pdf_url == str(local_pdf_path)
    assert document.page_count == 1
    assert len(chunks) == 1
    assert chunks[0].content == "This local PDF should be routed through uploaded PDF extraction."


@pytest.mark.asyncio
async def test_document_extraction_service_extracts_local_pdf_paths_without_http_when_openrouter_is_unconfigured(
    session_factory: async_sessionmaker[AsyncSession],
    sample_project: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_bytes = build_pdf_bytes(
        [
            (
                "1 Introduction\n\n"
                "This uploaded local PDF should still become retrievable chunks without HTTP."
            )
        ]
    )
    local_pdf_path = tmp_path / "offline-local.pdf"
    local_pdf_path.write_bytes(pdf_bytes)

    paper = await create_sample_paper(
        session_factory,
        project_id=sample_project["id"],
        pdf_url=str(local_pdf_path),
    )

    async with session_factory() as session:
        persisted_paper = await session.get(Paper, paper.id)
        assert persisted_paper is not None

        service = PaperDocumentExtractionService(
            api_key="placeholder-key",
            local_pdf_roots=[tmp_path],
            paper_chunk_size_chars=150,
            embedding_service=FakeEmbeddingService(),
        )

        async def fail_download(_: str) -> bytes:
            raise AssertionError("Local PDF paths should not use public HTTP download.")

        async def fail_openrouter(*, pdf_url: str, filename: str) -> ExtractedDocument:
            raise AssertionError(f"Local PDF path should not be sent to OpenRouter: {pdf_url}")

        monkeypatch.setattr(service, "_download_pdf", fail_download)
        monkeypatch.setattr(service, "_extract_with_openrouter", fail_openrouter)
        monkeypatch.setattr(
            service,
            "_extract_blocks_from_pdf_bytes",
            lambda _: (
                [
                    DocumentTextBlock(
                        page_number=1,
                        section_title="1 Introduction",
                        text=(
                            "This uploaded local PDF should still become retrievable chunks without "
                            "HTTP."
                        ),
                    )
                ],
                1,
            ),
        )

        await service.ensure_document_chunks(session=session, paper=persisted_paper)
        await session.commit()

    document, chunks = await load_document_and_chunks(session_factory, paper_id=paper.id)

    assert document is not None
    assert document.status == "ready"
    assert document.source_pdf_url == str(local_pdf_path)
    assert document.openrouter_file_hash is None
    assert document.page_count == 1
    assert document.error_message is None
    assert len(chunks) == 1
    assert chunks[0].page_start == 1
    assert chunks[0].page_end == 1
    assert chunks[0].section_title == "1 Introduction"
    assert chunks[0].embedding_json


@pytest.mark.asyncio
@respx.mock
async def test_document_extraction_service_persists_chunks_from_pdf(
    session_factory: async_sessionmaker[AsyncSession],
    sample_project: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_url = "https://papers.example.com/paper.pdf"
    pdf_bytes = build_pdf_bytes(
        [
            (
                "1 Introduction\n\n"
                "This page introduces the retrieval architecture for grounded paper conversations. "
                "It contains enough text to require chunking when the chunk size is small."
            ),
            (
                "2 Method\n\n"
                "The second page describes chunk persistence, page tracking, and embedding generation "
                "for follow-up retrieval quality checks."
            ),
        ]
    )
    respx.get(pdf_url).mock(
        return_value=httpx.Response(
            200,
            content=pdf_bytes,
            headers={"content-type": "application/pdf"},
        )
    )

    captured_request: dict[str, object] | None = None

    def openrouter_handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": "Acknowledged.",
                            "annotations": [
                                {
                                    "type": "file",
                                    "file": {
                                        "hash": "file-hash-123",
                                        "content": [
                                            {"type": "text", "text": "Parsed text content."}
                                        ],
                                    },
                                }
                            ],
                        },
                    }
                ]
            },
        )

    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        side_effect=openrouter_handler
    )

    paper = await create_sample_paper(
        session_factory,
        project_id=sample_project["id"],
        pdf_url=pdf_url,
    )

    async with session_factory() as session:
        persisted_paper = await session.get(Paper, paper.id)
        assert persisted_paper is not None

        service = PaperDocumentExtractionService(
            api_key="sk-or-test-key",
            model="google/gemini-2.5-flash-lite",
            paper_chunk_size_chars=120,
            embedding_service=FakeEmbeddingService(),
        )
        monkeypatch.setattr(
            service,
            "_extract_blocks_from_pdf_bytes",
            lambda _: (
                [
                    DocumentTextBlock(
                        page_number=1,
                        section_title="1 Introduction",
                        text=(
                            "This page introduces the retrieval architecture for grounded paper "
                            "conversations. It contains enough text to require chunking when the "
                            "chunk size is small."
                        ),
                    ),
                    DocumentTextBlock(
                        page_number=2,
                        section_title="2 Method",
                        text=(
                            "The second page describes chunk persistence, page tracking, and "
                            "embedding generation for follow-up retrieval quality checks."
                        ),
                    ),
                ],
                2,
            ),
        )
        await service.ensure_document_chunks(session=session, paper=persisted_paper)
        await session.commit()

    document, chunks = await load_document_and_chunks(session_factory, paper_id=paper.id)

    assert route.called
    assert captured_request is not None
    assert captured_request["model"] == "google/gemini-2.5-flash-lite"
    assert captured_request["plugins"] == [{"id": "file-parser", "pdf": {"engine": "native"}}]
    assert document is not None
    assert document.status == "ready"
    assert document.source_pdf_url == pdf_url
    assert document.openrouter_file_hash == "file-hash-123"
    assert document.page_count == 2
    assert document.error_message is None
    assert document.extracted_at is not None
    assert len(chunks) >= 2
    assert all(len(chunk.content) <= 120 for chunk in chunks)
    assert chunks[0].page_start == 1
    assert chunks[-1].page_end == 2
    assert chunks[0].embedding_json


@pytest.mark.asyncio
@respx.mock
async def test_document_extraction_service_retries_cloudflare_when_native_fails(
    session_factory: async_sessionmaker[AsyncSession],
    sample_project: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_url = "https://papers.example.com/retry.pdf"
    pdf_bytes = build_pdf_bytes(["Introduction\n\nRetry path content on one page."])
    respx.get(pdf_url).mock(return_value=httpx.Response(200, content=pdf_bytes))

    attempted_engines: list[str] = []

    def openrouter_handler(request: httpx.Request) -> httpx.Response:
        request_body = json.loads(request.content.decode("utf-8"))
        engine = request_body["plugins"][0]["pdf"]["engine"]
        attempted_engines.append(engine)
        if engine == "native":
            return httpx.Response(400, text="native parser unavailable")

        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": "Acknowledged.",
                            "annotations": [
                                {
                                    "type": "file",
                                    "file": {
                                        "hash": "retry-hash",
                                        "content": [{"type": "text", "text": "Parsed fallback text."}],
                                    },
                                }
                            ],
                        },
                    }
                ]
            },
        )

    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(side_effect=openrouter_handler)

    paper = await create_sample_paper(
        session_factory,
        project_id=sample_project["id"],
        pdf_url=pdf_url,
    )

    async with session_factory() as session:
        persisted_paper = await session.get(Paper, paper.id)
        assert persisted_paper is not None

        service = PaperDocumentExtractionService(
            api_key="sk-or-test-key",
            embedding_service=FakeEmbeddingService(),
        )
        monkeypatch.setattr(
            service,
            "_extract_blocks_from_pdf_bytes",
            lambda _: (
                [
                    DocumentTextBlock(
                        page_number=1,
                        section_title="Introduction",
                        text="Retry path content on one page.",
                    )
                ],
                1,
            ),
        )
        await service.ensure_document_chunks(session=session, paper=persisted_paper)
        await session.commit()

    document, chunks = await load_document_and_chunks(session_factory, paper_id=paper.id)

    assert attempted_engines == ["native", "cloudflare-ai"]
    assert document is not None
    assert document.status == "ready"
    assert document.openrouter_file_hash == "retry-hash"
    assert len(chunks) == 1


@pytest.mark.asyncio
@respx.mock
async def test_document_extraction_service_uses_local_pdf_fallback_without_openrouter(
    session_factory: async_sessionmaker[AsyncSession],
    sample_project: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_url = "https://papers.example.com/offline.pdf"
    pdf_bytes = build_pdf_bytes(
        [
            (
                "Offline Extraction\n\n"
                "This PDF should still become retrievable chunks when OpenRouter keys are absent."
            )
        ]
    )
    respx.get(pdf_url).mock(return_value=httpx.Response(200, content=pdf_bytes))

    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(500)
    )

    paper = await create_sample_paper(
        session_factory,
        project_id=sample_project["id"],
        pdf_url=pdf_url,
    )

    async with session_factory() as session:
        persisted_paper = await session.get(Paper, paper.id)
        assert persisted_paper is not None

        service = PaperDocumentExtractionService(
            api_key="placeholder-key",
            paper_chunk_size_chars=150,
            embedding_service=FakeEmbeddingService(),
        )
        monkeypatch.setattr(
            service,
            "_extract_blocks_from_pdf_bytes",
            lambda _: (
                [
                    DocumentTextBlock(
                        page_number=1,
                        text=(
                            "This PDF should still become retrievable chunks when OpenRouter keys "
                            "are absent."
                        ),
                        section_title="Offline Extraction",
                    )
                ],
                1,
            ),
        )
        await service.ensure_document_chunks(session=session, paper=persisted_paper)
        await session.commit()

    document, chunks = await load_document_and_chunks(session_factory, paper_id=paper.id)

    assert not route.called
    assert document is not None
    assert document.status == "ready"
    assert document.openrouter_file_hash is None
    assert document.page_count == 1
    assert len(chunks) == 1


@pytest.mark.asyncio
@respx.mock
async def test_document_extraction_service_strips_null_bytes_before_persisting(
    session_factory: async_sessionmaker[AsyncSession],
    sample_project: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_url = "https://papers.example.com/null-bytes.pdf"
    pdf_bytes = build_pdf_bytes(["placeholder"])
    respx.get(pdf_url).mock(
        return_value=httpx.Response(
            200,
            content=pdf_bytes,
            headers={"content-type": "application/pdf"},
        )
    )

    paper = await create_sample_paper(
        session_factory,
        project_id=sample_project["id"],
        pdf_url=pdf_url,
    )

    async with session_factory() as session:
        persisted_paper = await session.get(Paper, paper.id)
        assert persisted_paper is not None

        service = PaperDocumentExtractionService(
            api_key="placeholder-key",
            paper_chunk_size_chars=200,
            embedding_service=FakeEmbeddingService(),
        )
        monkeypatch.setattr(
            service,
            "_extract_blocks_from_pdf_bytes",
            lambda _: (
                service._build_blocks_from_text(
                    "1 Introduction\n\nThis text contains a null byte \x00 before persistence.",
                    page_number=1,
                ),
                1,
            ),
        )
        await service.ensure_document_chunks(session=session, paper=persisted_paper)
        await session.commit()

    document, chunks = await load_document_and_chunks(session_factory, paper_id=paper.id)

    assert document is not None
    assert document.status == "ready"
    assert len(chunks) == 1
    assert "\x00" not in chunks[0].content
    assert "null byte" in chunks[0].content


@pytest.mark.asyncio
@respx.mock
async def test_document_extraction_service_marks_document_failed_when_pdf_has_no_text(
    session_factory: async_sessionmaker[AsyncSession],
    sample_project: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_url = "https://papers.example.com/empty.pdf"
    pdf_bytes = build_pdf_bytes([""])
    respx.get(pdf_url).mock(return_value=httpx.Response(200, content=pdf_bytes))

    paper = await create_sample_paper(
        session_factory,
        project_id=sample_project["id"],
        pdf_url=pdf_url,
    )

    async with session_factory() as session:
        persisted_paper = await session.get(Paper, paper.id)
        assert persisted_paper is not None

        service = PaperDocumentExtractionService(
            api_key="placeholder-key",
            embedding_service=FakeEmbeddingService(),
        )
        monkeypatch.setattr(service, "_extract_blocks_from_pdf_bytes", lambda _: ([], 1))
        with pytest.raises(DocumentExtractionError, match="extractable text"):
            await service.ensure_document_chunks(session=session, paper=persisted_paper)
        await session.commit()

    document, chunks = await load_document_and_chunks(session_factory, paper_id=paper.id)

    assert document is not None
    assert document.status == "failed"
    assert document.error_message is not None
    assert chunks == []
