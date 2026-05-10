"""Tests for the writer document service and router (TDD)."""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.agents.writer_section import SectionDraftResult
from backend.db.models import Paper, Project, User, WriterDocument
from backend.security import hash_password
from backend.services.tavily import ACADEMIC_DOMAINS, TavilySearchResponse, TavilySearchResult
from backend.services.writer_documents import (
    WriterDocumentNotFoundError,
    WriterDocumentPermissionError,
    WriterDocumentService,
)


@pytest_asyncio.fixture
async def writer_user(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, str]:
    async with session_factory() as session:
        user = User(
            email="writer@example.com",
            hashed_password=hash_password("writerpass"),
            credit_balance=100_000,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return {"id": user.id, "email": user.email}


@pytest_asyncio.fixture
async def writer_project(
    session_factory: async_sessionmaker[AsyncSession],
    writer_user: dict[str, str],
) -> dict[str, str]:
    async with session_factory() as session:
        project = Project(
            user_id=writer_user["id"],
            title="Writer Test Project",
            topic_description="Testing writer workspace",
            citation_format="ieee",
            year_start=2018,
            candidate_limit=20,
            summary_limit=10,
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return {"id": project.id}


@pytest_asyncio.fixture
async def writer_auth_headers(writer_user: dict[str, str]) -> dict[str, str]:
    from backend.security import create_access_token

    token = create_access_token(writer_user["id"])
    return {"Authorization": f"Bearer {token}"}


class FakeTavilyService:
    def __init__(self, results: list[TavilySearchResult]) -> None:
        self.results = results
        self.calls: list[dict[str, object]] = []

    async def search(
        self,
        query: str,
        *,
        max_results: int | None = None,
        include_domains: list[str] | None = None,
    ) -> TavilySearchResponse:
        self.calls.append(
            {"query": query, "max_results": max_results, "include_domains": include_domains}
        )
        return TavilySearchResponse(results=self.results, warnings=[])


class FakeEmbeddingService:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    def embed_texts_locally(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


class FakeSourceRankerClient:
    def __init__(self, response: dict[str, Any] | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []
        self.prompt_payloads: list[dict[str, Any]] = []

    def is_configured(self) -> bool:
        return True

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        max_tokens: int = 1_024,
        feature: str = "structured_output",
    ) -> dict[str, Any]:
        import json

        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "schema": schema,
                "max_tokens": max_tokens,
                "feature": feature,
            }
        )
        self.prompt_payloads.append(json.loads(user_prompt))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class CapturingSectionAgent:
    def __init__(self) -> None:
        self.context_ids: list[str] = []

    async def draft_section(self, **kwargs: object) -> SectionDraftResult:
        paper_contexts = kwargs["paper_contexts"]
        self.context_ids = [context.paper_id for context in paper_contexts]  # type: ignore[attr-defined]
        return SectionDraftResult(
            draft_latex=r"\section{Introduction} Draft.",
            low_confidence_spans=[],
            cited_paper_ids=self.context_ids,
            warnings=[],
        )


class TestWriterDocumentService:
    async def test_create_document_creates_seven_sections(
        self, session_factory: async_sessionmaker[AsyncSession], writer_project: dict[str, str]
    ) -> None:
        svc = WriterDocumentService()
        async with session_factory() as session:
            doc = await svc.create_document(
                session=session,
                project_id=writer_project["id"],
                title="RAG Clinical QA",
                topic="retrieval-augmented generation for clinical QA",
                thesis="RAG improves clinical QA accuracy.",
                paper_type="imrad",
                citation_style="ieee",
            )
        assert isinstance(doc, WriterDocument)
        assert doc.title == "RAG Clinical QA"
        assert doc.status == "outline"
        assert len(doc.sections) == 7

    async def test_create_document_sections_in_order(
        self, session_factory: async_sessionmaker[AsyncSession], writer_project: dict[str, str]
    ) -> None:
        svc = WriterDocumentService()
        async with session_factory() as session:
            doc = await svc.create_document(
                session=session,
                project_id=writer_project["id"],
                title="Test",
                topic="testing",
                thesis=None,
            )
        section_types = [s.section_type for s in doc.sections]
        assert section_types == [
            "abstract",
            "intro",
            "related_work",
            "methods",
            "results",
            "discussion",
            "conclusion",
        ]

    async def test_get_document_wrong_user_raises_permission_error(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_project: dict[str, str],
    ) -> None:
        svc = WriterDocumentService()
        async with session_factory() as session:
            doc = await svc.create_document(
                session=session,
                project_id=writer_project["id"],
                title="Test",
                topic="testing",
                thesis=None,
            )
            doc_id = doc.id

        async with session_factory() as session:
            with pytest.raises(WriterDocumentPermissionError):
                await svc.get_document(
                    session=session, document_id=doc_id, user_id="wrong-user-id"
                )

    async def test_get_document_not_found_raises_error(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        svc = WriterDocumentService()
        async with session_factory() as session:
            with pytest.raises(WriterDocumentNotFoundError):
                await svc.get_document(
                    session=session, document_id="nonexistent-id", user_id="any"
                )

    async def test_propose_outline_returns_seven_sections(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_user: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        svc = WriterDocumentService()
        async with session_factory() as session:
            doc = await svc.create_document(
                session=session,
                project_id=writer_project["id"],
                title="Test",
                topic="machine learning",
                thesis="ML helps.",
            )
            doc_id = doc.id

        async with session_factory() as session:
            outline = await svc.propose_outline(
                session=session, document_id=doc_id, user_id=writer_user["id"]
            )
        assert len(outline) == 7
        for outline_text in outline.values():
            assert isinstance(outline_text, str)
            assert len(outline_text) > 0

    async def test_apply_outline_persists_and_sets_status(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_user: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        svc = WriterDocumentService()
        async with session_factory() as session:
            doc = await svc.create_document(
                session=session,
                project_id=writer_project["id"],
                title="Test",
                topic="federated learning",
                thesis=None,
            )
            doc_id = doc.id
            section_ids = [s.id for s in doc.sections]

        outline_by_section = {sid: f"Outline for {i}" for i, sid in enumerate(section_ids)}
        async with session_factory() as session:
            updated = await svc.apply_outline(
                session=session,
                document_id=doc_id,
                user_id=writer_user["id"],
                outline_by_section=outline_by_section,
            )
        assert updated.status == "drafting"
        for section in updated.sections:
            assert section.outline_text is not None
            assert section.status == "awaiting_input"

    async def test_submit_section_inputs_stores_answers(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_user: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        svc = WriterDocumentService()
        async with session_factory() as session:
            doc = await svc.create_document(
                session=session,
                project_id=writer_project["id"],
                title="Test",
                topic="adversarial examples",
                thesis=None,
            )
            methods_section = next(s for s in doc.sections if s.section_type == "methods")
            section_id = methods_section.id

        answers = {"What dataset(s) did you use?": "CIFAR-10", "What model/algorithm/approach?": "PGD"}
        async with session_factory() as session:
            section = await svc.submit_section_inputs(
                session=session,
                section_id=section_id,
                user_id=writer_user["id"],
                answers=answers,
            )
        assert section.user_inputs_json == answers
        assert section.status == "awaiting_input"

    async def test_get_section_questions_returns_list(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_user: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        svc = WriterDocumentService()
        async with session_factory() as session:
            doc = await svc.create_document(
                session=session,
                project_id=writer_project["id"],
                title="Test",
                topic="topic",
                thesis=None,
            )
            methods_section = next(s for s in doc.sections if s.section_type == "methods")
            section_id = methods_section.id

        async with session_factory() as session:
            _, questions = await svc.get_section_questions(
                session=session, section_id=section_id, user_id=writer_user["id"]
            )
        assert len(questions) == 4
        assert "What dataset(s) did you use?" in questions

    async def test_save_section_edit_snapshots_previous(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_user: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        svc = WriterDocumentService()
        async with session_factory() as session:
            doc = await svc.create_document(
                session=session,
                project_id=writer_project["id"],
                title="Test",
                topic="t",
                thesis=None,
            )
            section_id = doc.sections[1].id

        async with session_factory() as session:
            await svc.save_section_edit(
                session=session,
                section_id=section_id,
                user_id=writer_user["id"],
                draft_latex=r"\section{Intro} First draft.",
            )

        async with session_factory() as session:
            section = await svc.save_section_edit(
                session=session,
                section_id=section_id,
                user_id=writer_user["id"],
                draft_latex=r"\section{Intro} Second draft.",
            )
            versions = await svc.get_section_versions(
                session=session, section_id=section_id, user_id=writer_user["id"]
            )
        assert section.draft_latex == r"\section{Intro} Second draft."
        assert len(versions) >= 1

    async def test_remove_source_removes_paper_id(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_user: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        svc = WriterDocumentService()
        async with session_factory() as session:
            doc = await svc.create_document(
                session=session,
                project_id=writer_project["id"],
                title="Test",
                topic="t",
                thesis=None,
            )
            doc.source_paper_ids_json = ["paper-1", "paper-2"]
            await session.commit()
            doc_id = doc.id

        async with session_factory() as session:
            await svc.remove_source(
                session=session,
                document_id=doc_id,
                user_id=writer_user["id"],
                paper_id="paper-1",
            )
            doc = await svc.get_document(
                session=session, document_id=doc_id, user_id=writer_user["id"]
            )
        assert "paper-1" not in doc.source_paper_ids_json
        assert "paper-2" in doc.source_paper_ids_json

    async def test_attach_source_creates_metadata_paper_when_pdf_fetch_fails(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_user: dict[str, str],
        writer_project: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def fail_download_pdf(*args: object, **kwargs: object) -> bytes:
            raise RuntimeError("network timeout")

        monkeypatch.setattr("backend.services.writer_documents.download_pdf", fail_download_pdf)

        svc = WriterDocumentService()
        async with session_factory() as session:
            doc = await svc.create_document(
                session=session,
                project_id=writer_project["id"],
                title="Test",
                topic="retrieval augmented generation",
                thesis=None,
            )
            candidate = {
                "title": "Metadata Only Source",
                "authors": ["A. Researcher"],
                "year": 2024,
                "abstract": "Useful evidence for drafting.",
                "source": "tavily",
                "source_paper_id": None,
                "source_url": "https://example.com/source",
                "pdf_url": "https://example.com/source.pdf",
            }
            paper_id, requires_upload, message = await svc.attach_source(
                session=session,
                document_id=doc.id,
                user_id=writer_user["id"],
                candidate=candidate,
            )

            assert paper_id is not None
            assert requires_upload is False
            assert "metadata only" in message
            paper = await session.get(Paper, paper_id)
            assert paper is not None
            assert paper.source == "tavily"
            assert paper.abstract == "Useful evidence for drafting."

            reloaded = await svc.get_document(
                session=session, document_id=doc.id, user_id=writer_user["id"]
            )
            second_paper_id, second_requires_upload, second_message = await svc.attach_source(
                session=session,
                document_id=doc.id,
                user_id=writer_user["id"],
                candidate=candidate,
            )
            papers_with_url = list(
                (
                    await session.execute(
                        select(Paper).where(Paper.source_url == "https://example.com/source")
                    )
                )
                .scalars()
                .all()
            )
        assert paper_id in reloaded.source_paper_ids_json
        assert second_paper_id == paper_id
        assert second_requires_upload is False
        assert "already attached" in second_message
        assert len(papers_with_url) == 1

    async def test_suggest_sources_returns_top_seven_in_mimo_ranker_order(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_user: dict[str, str],
        writer_project: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def fake_arxiv_candidates(query: str, limit: int = 7) -> list[dict[str, Any]]:
            assert limit == 7
            return [
                {
                    "title": "Arxiv source 1",
                    "authors": ["A"],
                    "year": 2024,
                    "abstract": "retrieval augmented generation evidence",
                    "source": "arxiv",
                    "source_paper_id": "2401.00001",
                    "source_url": "https://arxiv.org/abs/2401.00001",
                    "pdf_url": "https://arxiv.org/pdf/2401.00001",
                },
                {
                    "title": "Arxiv source 2",
                    "authors": ["B"],
                    "year": 2023,
                    "abstract": "off topic robotics",
                    "source": "arxiv",
                    "source_paper_id": "2401.00002",
                    "source_url": "https://arxiv.org/abs/2401.00002",
                    "pdf_url": "https://arxiv.org/pdf/2401.00002",
                },
            ]

        tavily = FakeTavilyService(
            [
                TavilySearchResult(
                    title=f"Tavily source {idx}",
                    url=f"https://example.com/source-{idx}",
                    content="retrieval augmented generation clinical QA",
                    score=0.9 - (idx * 0.01),
                )
                for idx in range(1, 9)
            ]
        )
        ranker = FakeSourceRankerClient(
            {
                "ranked_candidates": [
                    {
                        "candidate_id": "cand_4",
                        "relevance_score": 0.99,
                        "keep": True,
                        "rationale": "best match",
                    },
                    {
                        "candidate_id": "cand_1",
                        "relevance_score": 0.95,
                        "keep": True,
                        "rationale": "academic match",
                    },
                    {
                        "candidate_id": "cand_2",
                        "relevance_score": 0.1,
                        "keep": False,
                        "rationale": "off topic",
                    },
                    {
                        "candidate_id": "cand_5",
                        "relevance_score": 0.9,
                        "keep": True,
                        "rationale": "useful",
                    },
                    {
                        "candidate_id": "cand_6",
                        "relevance_score": 0.89,
                        "keep": True,
                        "rationale": "useful",
                    },
                    {
                        "candidate_id": "cand_7",
                        "relevance_score": 0.88,
                        "keep": True,
                        "rationale": "useful",
                    },
                    {
                        "candidate_id": "cand_8",
                        "relevance_score": 0.87,
                        "keep": True,
                        "rationale": "useful",
                    },
                    {
                        "candidate_id": "cand_9",
                        "relevance_score": 0.86,
                        "keep": True,
                        "rationale": "useful",
                    },
                    {
                        "candidate_id": "cand_10",
                        "relevance_score": 0.85,
                        "keep": True,
                        "rationale": "extra",
                    },
                ],
                "warnings": [],
            }
        )
        svc = WriterDocumentService(tavily_service=tavily, source_ranker_client=ranker)
        monkeypatch.setattr(svc, "_fetch_arxiv_candidates", fake_arxiv_candidates)

        async with session_factory() as session:
            doc = await svc.create_document(
                session=session,
                project_id=writer_project["id"],
                title="RAG",
                topic="retrieval augmented generation",
                thesis="RAG improves clinical QA.",
            )
            candidates, warnings = await svc.suggest_sources(
                session=session,
                document_id=doc.id,
                user_id=writer_user["id"],
                query="clinical RAG",
            )

        assert warnings == []
        assert [candidate["title"] for candidate in candidates] == [
            "Tavily source 2",
            "Arxiv source 1",
            "Tavily source 3",
            "Tavily source 4",
            "Tavily source 5",
            "Tavily source 6",
            "Tavily source 7",
        ]
        assert "Arxiv source 2" not in [candidate["title"] for candidate in candidates]
        assert tavily.calls[0]["max_results"] == 12
        assert tavily.calls[0]["include_domains"] == ACADEMIC_DOMAINS
        assert ranker.calls[0]["feature"] == "writer_source_ranker"

    async def test_suggest_sources_dedupes_and_excludes_attached_sources_before_ranking(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_user: dict[str, str],
        writer_project: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def fake_arxiv_candidates(query: str, limit: int = 7) -> list[dict[str, Any]]:
            return [
                {
                    "title": "Already attached arxiv",
                    "authors": [],
                    "year": 2024,
                    "abstract": "attached",
                    "source": "arxiv",
                    "source_paper_id": "2401.00003",
                    "source_url": "https://arxiv.org/abs/2401.00003",
                    "pdf_url": "https://arxiv.org/pdf/2401.00003",
                },
                {
                    "title": "Unique arxiv",
                    "authors": [],
                    "year": 2024,
                    "abstract": "unique evidence",
                    "source": "arxiv",
                    "source_paper_id": "2401.00004",
                    "source_url": "https://arxiv.org/abs/2401.00004",
                    "pdf_url": "https://arxiv.org/pdf/2401.00004",
                },
                {
                    "title": "Duplicate arxiv URL",
                    "authors": [],
                    "year": 2024,
                    "abstract": "duplicate",
                    "source": "arxiv",
                    "source_paper_id": "2401.00004",
                    "source_url": "https://arxiv.org/abs/2401.00004v1",
                    "pdf_url": "https://arxiv.org/pdf/2401.00004v1",
                },
            ]

        tavily = FakeTavilyService(
            [
                TavilySearchResult(
                    title="Already attached URL",
                    url="https://example.com/attached/",
                    content="attached",
                    score=0.9,
                ),
                TavilySearchResult(
                    title="Unique web source",
                    url="https://example.com/unique?utm_source=test",
                    content="unique",
                    score=0.8,
                ),
                TavilySearchResult(
                    title="Duplicate web source",
                    url="https://example.com/unique",
                    content="duplicate",
                    score=0.7,
                ),
                TavilySearchResult(
                    title="",
                    url="https://example.com/no-title",
                    content="missing title",
                    score=0.6,
                ),
            ]
        )
        ranker = FakeSourceRankerClient(
            {
                "ranked_candidates": [
                    {"candidate_id": "cand_1", "relevance_score": 0.9, "keep": True, "rationale": ""},
                    {"candidate_id": "cand_2", "relevance_score": 0.8, "keep": True, "rationale": ""},
                ],
                "warnings": [],
            }
        )
        svc = WriterDocumentService(tavily_service=tavily, source_ranker_client=ranker)
        monkeypatch.setattr(svc, "_fetch_arxiv_candidates", fake_arxiv_candidates)

        async with session_factory() as session:
            doc = await svc.create_document(
                session=session,
                project_id=writer_project["id"],
                title="RAG",
                topic="retrieval augmented generation",
                thesis=None,
            )
            attached = Paper(
                project_id=writer_project["id"],
                title="Attached",
                authors=[],
                source="arxiv",
                source_paper_id="2401.00003",
                source_url="https://example.com/attached",
                status="candidate",
            )
            session.add(attached)
            await session.flush()
            doc.source_paper_ids_json = [attached.id]
            await session.commit()

            candidates, _ = await svc.suggest_sources(
                session=session,
                document_id=doc.id,
                user_id=writer_user["id"],
                query="clinical RAG",
            )

        prompt_candidates = ranker.prompt_payloads[0]["candidates"]
        assert [candidate["title"] for candidate in prompt_candidates] == [
            "Unique arxiv",
            "Unique web source",
        ]
        assert [candidate["title"] for candidate in candidates] == [
            "Unique arxiv",
            "Unique web source",
        ]

    async def test_suggest_sources_missing_xiaomi_key_uses_local_fallback_without_openrouter(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_user: dict[str, str],
        writer_project: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from backend.config import get_settings

        async def fake_arxiv_candidates(query: str, limit: int = 7) -> list[dict[str, Any]]:
            return []

        class ForbiddenOpenRouterClient:
            def __init__(self, **kwargs: object) -> None:
                raise AssertionError("source ranker must not fall back to OpenRouter")

        monkeypatch.setenv("XIAOMI_MIMO_API_KEY", "")
        get_settings.cache_clear()
        monkeypatch.setattr(
            "backend.services.writer_documents.OpenRouterStructuredOutputService",
            ForbiddenOpenRouterClient,
        )
        tavily = FakeTavilyService(
            [
                TavilySearchResult(
                    title="Relevant retrieval source",
                    url="https://example.com/relevant",
                    content="clinical retrieval augmented generation",
                    score=0.7,
                )
            ]
        )
        svc = WriterDocumentService(tavily_service=tavily)
        monkeypatch.setattr(svc, "_fetch_arxiv_candidates", fake_arxiv_candidates)

        async with session_factory() as session:
            doc = await svc.create_document(
                session=session,
                project_id=writer_project["id"],
                title="RAG",
                topic="clinical retrieval",
                thesis=None,
            )
            candidates, warnings = await svc.suggest_sources(
                session=session,
                document_id=doc.id,
                user_id=writer_user["id"],
                query="clinical retrieval",
            )

        assert warnings == []
        assert [candidate["title"] for candidate in candidates] == ["Relevant retrieval source"]
        get_settings.cache_clear()

    async def test_suggest_sources_invalid_mimo_output_falls_back_locally(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_user: dict[str, str],
        writer_project: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def fake_arxiv_candidates(query: str, limit: int = 7) -> list[dict[str, Any]]:
            return []

        tavily = FakeTavilyService(
            [
                TavilySearchResult(
                    title="Sparse unrelated source",
                    url="https://example.com/unrelated",
                    content="robot motion planning",
                    score=0.9,
                ),
                TavilySearchResult(
                    title="Clinical retrieval source",
                    url="https://example.com/clinical-retrieval",
                    content="clinical retrieval augmented generation QA",
                    score=0.2,
                ),
            ]
        )
        ranker = FakeSourceRankerClient({"ranked_candidates": "not-a-list", "warnings": []})
        svc = WriterDocumentService(tavily_service=tavily, source_ranker_client=ranker)
        monkeypatch.setattr(svc, "_fetch_arxiv_candidates", fake_arxiv_candidates)

        async with session_factory() as session:
            doc = await svc.create_document(
                session=session,
                project_id=writer_project["id"],
                title="RAG",
                topic="clinical retrieval",
                thesis=None,
            )
            candidates, warnings = await svc.suggest_sources(
                session=session,
                document_id=doc.id,
                user_id=writer_user["id"],
                query="clinical retrieval",
            )

        assert candidates[0]["title"] == "Clinical retrieval source"
        assert warnings == ["Source ranker returned invalid output; used local ranking."]

    async def test_attach_paper_id_requires_same_project_paper(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_user: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        svc = WriterDocumentService()
        async with session_factory() as session:
            other_project = Project(
                user_id=writer_user["id"],
                title="Other Project",
                topic_description="Other",
                citation_format="ieee",
                year_start=2018,
                candidate_limit=20,
                summary_limit=10,
            )
            doc = await svc.create_document(
                session=session,
                project_id=writer_project["id"],
                title="Test",
                topic="testing",
                thesis=None,
            )
            session.add(other_project)
            await session.flush()
            foreign_paper = Paper(
                project_id=other_project.id,
                title="Foreign Paper",
                authors=[],
                source="upload",
                status="candidate",
            )
            session.add(foreign_paper)
            await session.commit()

            with pytest.raises(WriterDocumentPermissionError):
                await svc.attach_paper_id(
                    session=session,
                    document_id=doc.id,
                    user_id=writer_user["id"],
                    paper_id=foreign_paper.id,
                )

    async def test_draft_section_auto_fetches_tavily_without_duplicate_source_urls(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_user: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        tavily = FakeTavilyService(
            [
                TavilySearchResult(
                    title="Existing URL",
                    url="https://example.com/existing",
                    content="Duplicate result.",
                    score=0.9,
                ),
                TavilySearchResult(
                    title="New URL",
                    url="https://example.com/new",
                    content="New evidence result.",
                    score=0.8,
                ),
            ]
        )
        section_agent = CapturingSectionAgent()
        svc = WriterDocumentService(
            tavily_service=tavily,
            embedding_service=FakeEmbeddingService(),
            section_agent=section_agent,
        )

        async with session_factory() as session:
            doc = await svc.create_document(
                session=session,
                project_id=writer_project["id"],
                title="Test",
                topic="clinical question answering",
                thesis=None,
            )
            intro_section = next(s for s in doc.sections if s.section_type == "intro")
            existing = Paper(
                project_id=writer_project["id"],
                title="Existing Paper",
                authors=[],
                source="tavily_auto",
                source_url="https://example.com/existing",
                abstract="Existing abstract.",
                status="candidate",
            )
            session.add(existing)
            await session.flush()
            doc.source_paper_ids_json = [existing.id]
            await session.commit()

            await svc.draft_section(
                session=session,
                section_id=intro_section.id,
                user_id=writer_user["id"],
            )

            papers = list(
                (
                    await session.execute(
                        select(Paper).where(Paper.project_id == writer_project["id"])
                    )
                )
                .scalars()
                .all()
            )
            reloaded = await svc.get_document(
                session=session, document_id=doc.id, user_id=writer_user["id"]
            )

        source_urls = [paper.source_url for paper in papers]
        assert source_urls.count("https://example.com/existing") == 1
        assert "https://example.com/new" in source_urls
        assert len(reloaded.source_paper_ids_json) == 2
        assert set(section_agent.context_ids) == set(reloaded.source_paper_ids_json)
        assert tavily.calls[0]["max_results"] == 12
        assert tavily.calls[0]["include_domains"] == ACADEMIC_DOMAINS

    async def test_draft_section_auto_fetches_tavily_top_seven_in_ranker_order(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_user: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        tavily = FakeTavilyService(
            [
                TavilySearchResult(
                    title=f"Auto source {idx}",
                    url=f"https://example.com/auto-{idx}",
                    content="clinical retrieval augmented generation evidence",
                    score=0.9 - (idx * 0.01),
                )
                for idx in range(1, 10)
            ]
        )
        ranker = FakeSourceRankerClient(
            {
                "ranked_candidates": [
                    {
                        "candidate_id": f"cand_{idx}",
                        "relevance_score": 1 - idx / 100,
                        "keep": True,
                        "rationale": "ranked",
                    }
                    for idx in (9, 8, 7, 6, 5, 4, 3, 2, 1)
                ],
                "warnings": [],
            }
        )
        section_agent = CapturingSectionAgent()
        svc = WriterDocumentService(
            tavily_service=tavily,
            source_ranker_client=ranker,
            embedding_service=FakeEmbeddingService(),
            section_agent=section_agent,
        )

        async with session_factory() as session:
            doc = await svc.create_document(
                session=session,
                project_id=writer_project["id"],
                title="RAG",
                topic="clinical retrieval",
                thesis="RAG improves QA.",
            )
            intro_section = next(s for s in doc.sections if s.section_type == "intro")
            await svc.submit_section_inputs(
                session=session,
                section_id=intro_section.id,
                user_id=writer_user["id"],
                answers={"__notes__": "prioritize recent clinical QA evidence"},
            )
            await svc.draft_section(
                session=session,
                section_id=intro_section.id,
                user_id=writer_user["id"],
            )
            reloaded = await svc.get_document(
                session=session, document_id=doc.id, user_id=writer_user["id"]
            )
            papers_by_id = {
                paper.id: paper
                for paper in (
                    await session.execute(
                        select(Paper).where(Paper.id.in_(reloaded.source_paper_ids_json))
                    )
                )
                .scalars()
                .all()
            }

        assert tavily.calls[0]["max_results"] == 12
        assert len(reloaded.source_paper_ids_json) == 7
        assert [papers_by_id[paper_id].title for paper_id in reloaded.source_paper_ids_json] == [
            "Auto source 9",
            "Auto source 8",
            "Auto source 7",
            "Auto source 6",
            "Auto source 5",
            "Auto source 4",
            "Auto source 3",
        ]
        assert section_agent.context_ids == reloaded.source_paper_ids_json
        assert ranker.prompt_payloads[0]["section"]["title"] == "Introduction"
        assert ranker.prompt_payloads[0]["section"]["user_answers"]["__notes__"] == (
            "prioritize recent clinical QA evidence"
        )

    async def test_assemble_substitutes_paper_uuid_citations_with_bibtex_keys(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_user: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        svc = WriterDocumentService()
        async with session_factory() as session:
            doc = await svc.create_document(
                session=session,
                project_id=writer_project["id"],
                title="Test",
                topic="neural retrieval",
                thesis=None,
            )
            paper = Paper(
                project_id=writer_project["id"],
                title="Neural Retrieval for Clinical QA",
                authors=["Jane Smith"],
                year=2024,
                source="upload",
                source_url="https://example.com/neural",
                status="candidate",
            )
            session.add(paper)
            await session.flush()
            doc.source_paper_ids_json = [paper.id]
            section = doc.sections[1]
            section.draft_latex = f"\\section{{Introduction}} Grounded claim. \\cite{{{paper.id}}}"
            await session.commit()

            result = await svc.assemble(
                session=session,
                document_id=doc.id,
                user_id=writer_user["id"],
            )

        assert f"\\cite{{{paper.id}}}" not in result.tex
        assert r"\cite{smith2024neural}" in result.tex
        assert "@misc{smith2024neural," in result.bib

    async def test_assemble_backfills_references_from_draft_citations(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_user: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        svc = WriterDocumentService()
        async with session_factory() as session:
            doc = await svc.create_document(
                session=session,
                project_id=writer_project["id"],
                title="Test",
                topic="badminton shuttlecock tracking",
                thesis=None,
            )
            paper = Paper(
                project_id=writer_project["id"],
                title="TrackNet for Badminton",
                authors=["Alice Chen"],
                year=2023,
                source="tavily_auto",
                source_url="https://example.com/tracknet-badminton",
                status="candidate",
            )
            session.add(paper)
            await session.flush()
            section = doc.sections[1]
            section.draft_latex = (
                f"\\section{{Introduction}} Badminton needs specific tracking. "
                f"\\citep{{{paper.id}}}"
            )
            await session.commit()

            result = await svc.assemble(
                session=session,
                document_id=doc.id,
                user_id=writer_user["id"],
            )
            reloaded = await svc.get_document(
                session=session,
                document_id=doc.id,
                user_id=writer_user["id"],
            )

        assert f"\\citep{{{paper.id}}}" not in result.tex
        assert r"\citep{chen2023tracknet}" in result.tex
        assert "@misc{chen2023tracknet," in result.bib
        assert paper.id in reloaded.source_paper_ids_json

    async def test_get_qa_report_empty_document(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_user: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        svc = WriterDocumentService()
        async with session_factory() as session:
            doc = await svc.create_document(
                session=session,
                project_id=writer_project["id"],
                title="Test",
                topic="t",
                thesis=None,
            )
            report = svc.get_qa_report(doc)
        assert report["total_count"] == 0
        assert report["unresolved_todos"] == []

    async def test_delete_document(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_user: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        svc = WriterDocumentService()
        async with session_factory() as session:
            doc = await svc.create_document(
                session=session,
                project_id=writer_project["id"],
                title="Delete me",
                topic="t",
                thesis=None,
            )
            doc_id = doc.id

        async with session_factory() as session:
            await svc.delete_document(
                session=session, document_id=doc_id, user_id=writer_user["id"]
            )

        async with session_factory() as session:
            with pytest.raises(WriterDocumentNotFoundError):
                await svc.get_document(
                    session=session, document_id=doc_id, user_id=writer_user["id"]
                )


class TestWriterDocumentRouter:
    async def test_create_document_endpoint(
        self,
        client: AsyncClient,
        writer_auth_headers: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        response = await client.post(
            f"/projects/{writer_project['id']}/writer/documents",
            json={
                "topic": "retrieval augmented generation",
                "thesis": "RAG improves accuracy.",
                "title": "My RAG Paper",
            },
            headers=writer_auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "My RAG Paper"
        assert data["status"] == "outline"
        assert len(data["sections"]) == 7

    async def test_list_documents_endpoint(
        self,
        client: AsyncClient,
        writer_auth_headers: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        await client.post(
            f"/projects/{writer_project['id']}/writer/documents",
            json={"topic": "test topic", "title": "Test"},
            headers=writer_auth_headers,
        )
        response = await client.get(
            f"/projects/{writer_project['id']}/writer/documents",
            headers=writer_auth_headers,
        )
        assert response.status_code == 200
        assert len(response.json()) >= 1

    async def test_get_document_endpoint(
        self,
        client: AsyncClient,
        writer_auth_headers: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        create_resp = await client.post(
            f"/projects/{writer_project['id']}/writer/documents",
            json={"topic": "test topic", "title": "Test"},
            headers=writer_auth_headers,
        )
        doc_id = create_resp.json()["id"]
        response = await client.get(
            f"/writer/documents/{doc_id}",
            headers=writer_auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["id"] == doc_id

    async def test_update_document_endpoint(
        self,
        client: AsyncClient,
        writer_auth_headers: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        create_resp = await client.post(
            f"/projects/{writer_project['id']}/writer/documents",
            json={"topic": "test topic", "title": "Old Title"},
            headers=writer_auth_headers,
        )
        doc_id = create_resp.json()["id"]
        response = await client.patch(
            f"/writer/documents/{doc_id}",
            json={"title": "New Title"},
            headers=writer_auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["title"] == "New Title"

    async def test_delete_document_endpoint(
        self,
        client: AsyncClient,
        writer_auth_headers: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        create_resp = await client.post(
            f"/projects/{writer_project['id']}/writer/documents",
            json={"topic": "test topic", "title": "Delete Me"},
            headers=writer_auth_headers,
        )
        doc_id = create_resp.json()["id"]
        response = await client.delete(
            f"/writer/documents/{doc_id}",
            headers=writer_auth_headers,
        )
        assert response.status_code == 204

        get_resp = await client.get(
            f"/writer/documents/{doc_id}",
            headers=writer_auth_headers,
        )
        assert get_resp.status_code == 404

    async def test_propose_outline_endpoint(
        self,
        client: AsyncClient,
        writer_auth_headers: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        create_resp = await client.post(
            f"/projects/{writer_project['id']}/writer/documents",
            json={"topic": "deep learning", "title": "DL Paper"},
            headers=writer_auth_headers,
        )
        doc_id = create_resp.json()["id"]
        response = await client.post(
            f"/writer/documents/{doc_id}/outline/propose",
            headers=writer_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "outline_by_section" in data
        assert len(data["outline_by_section"]) == 7

    async def test_apply_outline_endpoint(
        self,
        client: AsyncClient,
        writer_auth_headers: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        create_resp = await client.post(
            f"/projects/{writer_project['id']}/writer/documents",
            json={"topic": "NLP", "title": "NLP Paper"},
            headers=writer_auth_headers,
        )
        doc = create_resp.json()
        doc_id = doc["id"]
        section_ids = [s["id"] for s in doc["sections"]]
        outline = {sid: f"Outline for section {i}" for i, sid in enumerate(section_ids)}
        response = await client.put(
            f"/writer/documents/{doc_id}/outline",
            json={"outline_by_section": outline},
            headers=writer_auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "drafting"

    async def test_section_questions_endpoint(
        self,
        client: AsyncClient,
        writer_auth_headers: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        create_resp = await client.post(
            f"/projects/{writer_project['id']}/writer/documents",
            json={"topic": "reinforcement learning", "title": "RL Paper"},
            headers=writer_auth_headers,
        )
        assert create_resp.status_code == 201, f"Create failed: {create_resp.text}"
        doc = create_resp.json()
        doc_id = doc["id"]
        methods_section = next(s for s in doc["sections"] if s["section_type"] == "methods")
        section_id = methods_section["id"]
        response = await client.get(
            f"/writer/documents/{doc_id}/sections/{section_id}/questions",
            headers=writer_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["questions"]) == 4

    async def test_submit_section_inputs_endpoint(
        self,
        client: AsyncClient,
        writer_auth_headers: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        create_resp = await client.post(
            f"/projects/{writer_project['id']}/writer/documents",
            json={"topic": "reinforcement learning", "title": "RL Paper"},
            headers=writer_auth_headers,
        )
        doc = create_resp.json()
        doc_id = doc["id"]
        methods_section = next(s for s in doc["sections"] if s["section_type"] == "methods")
        section_id = methods_section["id"]
        response = await client.put(
            f"/writer/documents/{doc_id}/sections/{section_id}/inputs",
            json={"user_inputs": {"What dataset(s) did you use?": "CartPole"}},
            headers=writer_auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "awaiting_input"

    async def test_save_section_edit_endpoint(
        self,
        client: AsyncClient,
        writer_auth_headers: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        create_resp = await client.post(
            f"/projects/{writer_project['id']}/writer/documents",
            json={"topic": "computer vision", "title": "CV Paper"},
            headers=writer_auth_headers,
        )
        doc = create_resp.json()
        doc_id = doc["id"]
        section_id = doc["sections"][1]["id"]
        response = await client.patch(
            f"/writer/documents/{doc_id}/sections/{section_id}",
            json={"draft_latex": r"\section{Intro} My custom draft."},
            headers=writer_auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["draft_latex"] == r"\section{Intro} My custom draft."
        assert response.json()["status"] == "user_edited"

    async def test_qa_report_endpoint(
        self,
        client: AsyncClient,
        writer_auth_headers: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        create_resp = await client.post(
            f"/projects/{writer_project['id']}/writer/documents",
            json={"topic": "generative adversarial networks", "title": "GAN Paper"},
            headers=writer_auth_headers,
        )
        doc_id = create_resp.json()["id"]
        response = await client.get(
            f"/writer/documents/{doc_id}/qa",
            headers=writer_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_count" in data
        assert data["total_count"] == 0

    async def test_remove_source_endpoint(
        self,
        client: AsyncClient,
        writer_auth_headers: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        create_resp = await client.post(
            f"/projects/{writer_project['id']}/writer/documents",
            json={"topic": "graph neural networks", "title": "GNN Paper"},
            headers=writer_auth_headers,
        )
        doc_id = create_resp.json()["id"]
        response = await client.delete(
            f"/writer/documents/{doc_id}/sources/nonexistent-paper",
            headers=writer_auth_headers,
        )
        assert response.status_code == 204

    async def test_unauthenticated_request_rejected(
        self,
        client: AsyncClient,
        writer_project: dict[str, str],
    ) -> None:
        response = await client.get(
            f"/projects/{writer_project['id']}/writer/documents"
        )
        assert response.status_code == 401
