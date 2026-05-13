"""Tests for the writer document service and router (TDD)."""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.agents.writer_section import SectionDraftResult
from backend.db.models import Paper, Project, User, WriterDocument, WriterDocumentSource
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
    def __init__(
        self,
        results: list[TavilySearchResult],
        warnings: list[str] | None = None,
    ) -> None:
        self.results = results
        self.warnings = warnings or []
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
        return TavilySearchResponse(results=self.results, warnings=list(self.warnings))


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
        self.calls: list[dict[str, object]] = []

    async def draft_section(self, **kwargs: object) -> SectionDraftResult:
        self.calls.append(kwargs)
        paper_contexts = kwargs["paper_contexts"]
        self.context_ids = [context.paper_id for context in paper_contexts]  # type: ignore[attr-defined]
        return SectionDraftResult(
            draft_latex=r"\section{Introduction} Draft.",
            low_confidence_spans=[],
            cited_paper_ids=self.context_ids,
            warnings=[],
        )


class TestWriterDocumentService:
    async def test_create_standalone_document_is_user_owned_without_project(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_user: dict[str, str],
    ) -> None:
        svc = WriterDocumentService()
        async with session_factory() as session:
            doc = await svc.create_document(
                session=session,
                user_id=writer_user["id"],
                project_id=None,
                title="Standalone Survey",
                topic="high-speed object tracking",
                thesis=None,
                paper_type="survey",
                citation_style="ieee",
            )

        assert doc.user_id == writer_user["id"]
        assert doc.project_id is None
        assert doc.title == "Standalone Survey"
        assert len(doc.sections) == 7

    async def test_standalone_document_sources_are_document_owned(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_user: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def fail_download_pdf(*args: object, **kwargs: object) -> bytes:
            raise RuntimeError("network timeout")

        monkeypatch.setattr("backend.services.writer_documents.download_pdf", fail_download_pdf)

        svc = WriterDocumentService()
        async with session_factory() as session:
            doc = await svc.create_document(
                session=session,
                user_id=writer_user["id"],
                project_id=None,
                title="Standalone",
                topic="high-speed tracking",
                thesis=None,
            )
            paper_id, requires_upload, _ = await svc.attach_source(
                session=session,
                document_id=doc.id,
                user_id=writer_user["id"],
                candidate={
                    "title": "Standalone Source",
                    "authors": ["A. Researcher"],
                    "year": 2025,
                    "abstract": "Evidence for standalone drafting.",
                    "source": "tavily",
                    "source_url": "https://example.com/standalone",
                    "pdf_url": "https://example.com/standalone.pdf",
                },
            )
            assert paper_id is not None
            link_rows = list(
                (
                    await session.execute(
                        select(WriterDocumentSource).where(
                            WriterDocumentSource.writer_document_id == doc.id
                        )
                    )
                )
                .scalars()
                .all()
            )
            paper = await session.get(Paper, paper_id)

        assert requires_upload is False
        assert paper is not None
        assert paper.user_id == writer_user["id"]
        assert paper.project_id is None
        assert len(link_rows) == 1
        assert link_rows[0].paper_id == paper_id
        assert link_rows[0].source_origin == "tavily"

    async def test_draft_section_uses_document_sources_without_project(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_user: dict[str, str],
    ) -> None:
        tavily = FakeTavilyService([])
        section_agent = CapturingSectionAgent()
        svc = WriterDocumentService(
            tavily_service=tavily,
            embedding_service=FakeEmbeddingService(),
            section_agent=section_agent,
        )

        async with session_factory() as session:
            doc = await svc.create_document(
                session=session,
                user_id=writer_user["id"],
                project_id=None,
                title="Standalone",
                topic="clinical retrieval",
                thesis=None,
            )
            paper = Paper(
                user_id=writer_user["id"],
                project_id=None,
                title="Standalone Evidence",
                authors=[],
                source="manual",
                abstract="Standalone evidence.",
                status="candidate",
            )
            session.add(paper)
            await session.flush()
            await svc.attach_paper_id(
                session=session,
                document_id=doc.id,
                user_id=writer_user["id"],
                paper_id=paper.id,
            )
            intro_section = next(s for s in doc.sections if s.section_type == "intro")
            intro_section.outline_text = "Frame the clinical retrieval problem."
            await session.flush()

            section, warnings = await svc.draft_section(
                session=session,
                section_id=intro_section.id,
                user_id=writer_user["id"],
            )

        assert section.draft_latex
        assert warnings == []
        assert section_agent.context_ids == [paper.id]

    async def test_import_project_sources_copies_owned_project_papers_to_document(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_user: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        svc = WriterDocumentService()
        async with session_factory() as session:
            project_paper = Paper(
                project_id=writer_project["id"],
                title="Project Source",
                authors=["A. Author"],
                year=2024,
                abstract="Project evidence.",
                source="semantic_scholar",
                source_paper_id="S2-1",
                source_url="https://example.com/project-source",
                status="candidate",
            )
            session.add(project_paper)
            await session.flush()
            doc = await svc.create_document(
                session=session,
                user_id=writer_user["id"],
                project_id=None,
                title="Standalone",
                topic="tracking",
                thesis=None,
            )
            imported_ids = await svc.import_project_sources(
                session=session,
                document_id=doc.id,
                user_id=writer_user["id"],
                project_id=writer_project["id"],
                paper_ids=[project_paper.id],
            )
            imported = await session.get(Paper, imported_ids[0])
            source_rows = list(
                (
                    await session.execute(
                        select(WriterDocumentSource).where(
                            WriterDocumentSource.writer_document_id == doc.id
                        )
                    )
                )
                .scalars()
                .all()
            )

        assert imported is not None
        assert imported.id != project_paper.id
        assert imported.user_id == writer_user["id"]
        assert imported.project_id is None
        assert imported.title == "Project Source"
        assert source_rows[0].paper_id == imported.id
        assert source_rows[0].source_origin == "project_import"

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

    async def test_research_methods_section_outline_uses_subsections(
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
                title="Research Paper",
                topic="high-speed object tracking",
                thesis=None,
                paper_type="research",
            )
            methods_section = next(s for s in doc.sections if s.section_type == "methods")
            section_id = methods_section.id

        async with session_factory() as session:
            _, outline = await svc.propose_section_outline(
                session=session,
                section_id=section_id,
                user_id=writer_user["id"],
            )

        assert r"\subsection{Study Design and Experimental Setup}" in outline
        assert r"\subsection{Proposed Method}" in outline
        assert r"\subsection{Evaluation Metrics}" in outline

    async def test_survey_methods_section_outline_uses_review_protocol_subsections(
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
                title="Survey Paper",
                topic="high-speed object tracking",
                thesis=None,
                paper_type="survey",
            )
            methods_section = next(s for s in doc.sections if s.section_type == "methods")
            section_id = methods_section.id

        async with session_factory() as session:
            _, outline = await svc.propose_section_outline(
                session=session,
                section_id=section_id,
                user_id=writer_user["id"],
            )

        assert r"\subsection{Survey Scope and Research Questions}" in outline
        assert r"\subsection{Literature Search and Selection Criteria}" in outline
        assert r"\subsection{Tracking Method Taxonomy}" in outline
        assert "Describe the methodology used" not in outline

    async def test_research_results_section_outline_uses_result_subsections(
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
                title="Research Paper",
                topic="high-speed object tracking",
                thesis=None,
                paper_type="research",
            )
            results_section = next(s for s in doc.sections if s.section_type == "results")
            section_id = results_section.id

        async with session_factory() as session:
            _, outline = await svc.propose_section_outline(
                session=session,
                section_id=section_id,
                user_id=writer_user["id"],
            )

        assert r"\subsection{Primary Quantitative Findings}" in outline
        assert r"\subsection{Baseline and Comparator Results}" in outline
        assert r"\subsection{Qualitative Findings and Error Cases}" in outline
        assert "Present quantitative and qualitative results" not in outline

    async def test_survey_results_section_outline_uses_comparative_subsections(
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
                title="Survey Paper",
                topic="high-speed object tracking",
                thesis=None,
                paper_type="survey",
            )
            results_section = next(s for s in doc.sections if s.section_type == "results")
            section_id = results_section.id

        async with session_factory() as session:
            _, outline = await svc.propose_section_outline(
                session=session,
                section_id=section_id,
                user_id=writer_user["id"],
            )

        assert r"\subsection{Comparative Findings by Method Family}" in outline
        assert r"\subsection{Performance Under High-Speed Conditions}" in outline
        assert r"\subsection{Accuracy, Robustness, and Latency Trade-offs}" in outline
        assert "Present comparative patterns" not in outline

    async def test_survey_methods_draft_rejects_generic_one_line_outline(
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
                title="Survey Paper",
                topic="high-speed object tracking",
                thesis=None,
                paper_type="survey",
            )
            methods_section = next(s for s in doc.sections if s.section_type == "methods")
            methods_section.outline_text = "Describe the methodology used in the survey study."
            await session.commit()
            section_id = methods_section.id

        async with session_factory() as session:
            with pytest.raises(ValueError, match="Approve a structured Methods outline"):
                await svc.draft_section(
                    session=session,
                    section_id=section_id,
                    user_id=writer_user["id"],
                )

    async def test_survey_results_draft_rejects_generic_one_line_outline(
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
                title="Survey Paper",
                topic="high-speed object tracking",
                thesis=None,
                paper_type="survey",
            )
            results_section = next(s for s in doc.sections if s.section_type == "results")
            results_section.outline_text = "Present comparative patterns across method families."
            await session.commit()
            section_id = results_section.id

        async with session_factory() as session:
            with pytest.raises(ValueError, match="Approve a structured Results outline"):
                await svc.draft_section(
                    session=session,
                    section_id=section_id,
                    user_id=writer_user["id"],
                )

    async def test_approve_section_outline_persists_single_section(
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
                title="Research Paper",
                topic="high-speed object tracking",
                thesis=None,
                paper_type="research",
            )
            methods_section = next(s for s in doc.sections if s.section_type == "methods")
            section_id = methods_section.id

        outline = r"\subsection{Proposed Method}"
        async with session_factory() as session:
            section = await svc.approve_section_outline(
                session=session,
                section_id=section_id,
                user_id=writer_user["id"],
                outline_text=outline,
            )

        assert section.outline_text == outline
        assert section.status == "awaiting_input"

    async def test_draft_section_requires_approved_outline(
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
                title="Research Paper",
                topic="high-speed object tracking",
                thesis=None,
                paper_type="research",
            )
            methods_section = next(s for s in doc.sections if s.section_type == "methods")
            section_id = methods_section.id

        async with session_factory() as session:
            with pytest.raises(ValueError, match="Approve a section outline before drafting"):
                await svc.draft_section(
                    session=session,
                    section_id=section_id,
                    user_id=writer_user["id"],
                )

    async def test_draft_section_passes_approved_outline_to_section_agent(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_user: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        capturing_agent = CapturingSectionAgent()
        svc = WriterDocumentService(
            section_agent=capturing_agent,
            embedding_service=FakeEmbeddingService(),
            tavily_service=FakeTavilyService([]),
        )
        outline = r"\subsection{Proposed Method}"
        async with session_factory() as session:
            doc = await svc.create_document(
                session=session,
                project_id=writer_project["id"],
                title="Research Paper",
                topic="high-speed object tracking",
                thesis=None,
                paper_type="research",
            )
            methods_section = next(s for s in doc.sections if s.section_type == "methods")
            paper = Paper(
                project_id=writer_project["id"],
                title="Tracking Method Paper",
                authors=["A. Researcher"],
                year=2025,
                abstract="A paper about tracking methods.",
                source="manual",
                status="candidate",
            )
            session.add(paper)
            await session.flush()
            doc.source_paper_ids_json = [paper.id]
            methods_section.outline_text = outline
            await session.commit()
            section_id = methods_section.id

        async with session_factory() as session:
            await svc.draft_section(
                session=session,
                section_id=section_id,
                user_id=writer_user["id"],
            )

        assert capturing_agent.calls
        assert capturing_agent.calls[0]["outline_text"] == outline
        assert capturing_agent.calls[0]["paper_type"] == "research"

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

    async def test_suggest_sources_accepts_mimo_candidates_alias(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_user: dict[str, str],
        writer_project: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
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
        ranker = FakeSourceRankerClient(
            {
                "candidates": [
                    {
                        "candidate_id": "cand_1",
                        "relevance_score": 0.98,
                        "keep": True,
                        "rationale": "provider alias order",
                    },
                    {
                        "candidate_id": "cand_2",
                        "relevance_score": 0.97,
                        "keep": True,
                        "rationale": "provider alias order",
                    },
                ],
                "warnings": [],
            }
        )
        svc = WriterDocumentService(tavily_service=tavily, source_ranker_client=ranker)
        monkeypatch.setattr(svc, "_fetch_arxiv_candidates", fake_arxiv_candidates)
        caplog.set_level("WARNING", logger="backend.services.writer_documents")

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
        assert [candidate["title"] for candidate in candidates] == [
            "Sparse unrelated source",
            "Clinical retrieval source",
        ]
        assert not any(
            record.message.startswith("Source ranker returned invalid provider payload")
            for record in caplog.records
        )

    async def test_suggest_sources_invalid_mimo_output_falls_back_locally(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_user: dict[str, str],
        writer_project: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
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
        caplog.set_level("WARNING", logger="backend.services.writer_documents")

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
        log_record = next(
            record
            for record in caplog.records
            if record.message.startswith("Source ranker returned invalid provider payload")
        )
        assert log_record.payload_shape == {
            "ranked_candidates_type": "str",
            "top_level_keys": ["ranked_candidates", "warnings"],
            "warnings_type": "list",
        }
        assert "Sparse unrelated source" not in log_record.message

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
            intro_section.outline_text = "Frame the clinical question answering problem."
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

            reloaded = await svc.get_document(
                session=session, document_id=doc.id, user_id=writer_user["id"]
            )
            papers = list(
                (
                    await session.execute(
                        select(Paper).where(Paper.id.in_(reloaded.source_paper_ids_json))
                    )
                )
                .scalars()
                .all()
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
            intro_section.outline_text = "Frame the clinical retrieval problem."
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

    async def test_draft_section_auto_fetches_arxiv_when_tavily_returns_no_sources(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_user: dict[str, str],
        writer_project: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def fake_arxiv_candidates(query: str, limit: int = 7) -> list[dict[str, Any]]:
            assert limit == 7
            assert "clinical retrieval" in query
            return [
                {
                    "title": "Arxiv Auto Source",
                    "authors": ["A. Author"],
                    "year": 2024,
                    "abstract": "clinical retrieval augmented generation evidence",
                    "source": "arxiv",
                    "source_paper_id": "2401.00001",
                    "source_url": "https://arxiv.org/abs/2401.00001",
                    "pdf_url": "https://arxiv.org/pdf/2401.00001",
                }
            ]

        tavily = FakeTavilyService(
            [],
            warnings=["Tavily API key is not configured; web search was skipped."],
        )
        section_agent = CapturingSectionAgent()
        svc = WriterDocumentService(
            tavily_service=tavily,
            embedding_service=FakeEmbeddingService(),
            section_agent=section_agent,
        )
        monkeypatch.setattr(svc, "_fetch_arxiv_candidates", fake_arxiv_candidates)

        async with session_factory() as session:
            doc = await svc.create_document(
                session=session,
                project_id=writer_project["id"],
                title="RAG",
                topic="clinical retrieval",
                thesis=None,
            )
            intro_section = next(s for s in doc.sections if s.section_type == "intro")
            intro_section.outline_text = "Frame the clinical retrieval problem."
            section, warnings = await svc.draft_section(
                session=session,
                section_id=intro_section.id,
                user_id=writer_user["id"],
            )
            reloaded = await svc.get_document(
                session=session, document_id=doc.id, user_id=writer_user["id"]
            )
            stored_papers = list(
                (
                    await session.execute(
                        select(Paper).where(Paper.id.in_(reloaded.source_paper_ids_json))
                    )
                )
                .scalars()
                .all()
            )

        assert section.draft_latex
        assert warnings == []
        assert [paper.title for paper in stored_papers] == ["Arxiv Auto Source"]
        assert reloaded.source_paper_ids_json == [stored_papers[0].id]
        assert section_agent.context_ids == reloaded.source_paper_ids_json

    async def test_draft_section_reports_auto_search_warnings_when_no_sources_found(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        writer_user: dict[str, str],
        writer_project: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def fail_arxiv_candidates(query: str, limit: int = 7) -> list[dict[str, Any]]:
            raise RuntimeError("arXiv timeout")

        tavily = FakeTavilyService(
            [],
            warnings=["Tavily API key is not configured; web search was skipped."],
        )
        svc = WriterDocumentService(tavily_service=tavily)
        monkeypatch.setattr(svc, "_fetch_arxiv_candidates", fail_arxiv_candidates)

        async with session_factory() as session:
            doc = await svc.create_document(
                session=session,
                project_id=writer_project["id"],
                title="RAG",
                topic="clinical retrieval",
                thesis=None,
            )
            intro_section = next(s for s in doc.sections if s.section_type == "intro")
            intro_section.outline_text = "Frame the clinical retrieval problem."
            section, warnings = await svc.draft_section(
                session=session,
                section_id=intro_section.id,
                user_id=writer_user["id"],
            )

        assert section.draft_latex == ""
        assert "arXiv unavailable: arXiv timeout" in warnings
        assert "Tavily API key is not configured; web search was skipped." in warnings
        assert "No source papers attached" in warnings[-1]

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
    async def test_create_standalone_document_endpoint(
        self,
        client: AsyncClient,
        writer_auth_headers: dict[str, str],
    ) -> None:
        response = await client.post(
            "/writer/documents",
            json={
                "topic": "high-speed moving object tracking",
                "title": "Independent Survey",
                "paper_type": "survey",
            },
            headers=writer_auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["project_id"] is None
        assert data["title"] == "Independent Survey"
        assert len(data["sections"]) == 7

    async def test_list_standalone_writer_documents_endpoint(
        self,
        client: AsyncClient,
        writer_auth_headers: dict[str, str],
    ) -> None:
        await client.post(
            "/writer/documents",
            json={"topic": "test topic", "title": "Standalone Test"},
            headers=writer_auth_headers,
        )

        response = await client.get("/writer/documents", headers=writer_auth_headers)

        assert response.status_code == 200
        assert [doc["title"] for doc in response.json()] == ["Standalone Test"]

    async def test_import_project_sources_rejects_other_users_project(
        self,
        client: AsyncClient,
        writer_auth_headers: dict[str, str],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        create_resp = await client.post(
            "/writer/documents",
            json={"topic": "test topic", "title": "Standalone"},
            headers=writer_auth_headers,
        )
        doc_id = create_resp.json()["id"]

        async with session_factory() as session:
            other_user = User(
                email="other-project-owner@example.com",
                hashed_password=hash_password("writerpass"),
                credit_balance=100_000,
            )
            session.add(other_user)
            await session.flush()
            other_project = Project(
                user_id=other_user.id,
                title="Other Project",
                topic_description="Other topic",
                citation_format="ieee",
                year_start=2018,
                candidate_limit=20,
                summary_limit=10,
            )
            session.add(other_project)
            await session.flush()
            paper = Paper(
                project_id=other_project.id,
                title="Other Paper",
                authors=[],
                source="semantic_scholar",
                status="candidate",
            )
            session.add(paper)
            await session.commit()

        response = await client.post(
            f"/writer/documents/{doc_id}/sources/import-project",
            json={"project_id": other_project.id, "paper_ids": [paper.id]},
            headers=writer_auth_headers,
        )

        assert response.status_code == 403

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

    async def test_get_document_endpoint_includes_attached_source_metadata(
        self,
        client: AsyncClient,
        writer_auth_headers: dict[str, str],
        writer_project: dict[str, str],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        create_resp = await client.post(
            f"/projects/{writer_project['id']}/writer/documents",
            json={"topic": "test topic", "title": "Test"},
            headers=writer_auth_headers,
        )
        doc_id = create_resp.json()["id"]

        async with session_factory() as session:
            paper = Paper(
                project_id=writer_project["id"],
                title="Human-readable attached source",
                authors=["A. Scholar"],
                year=2025,
                abstract="A source abstract.",
                source="semantic_scholar",
                source_paper_id="S2-123",
                source_url="https://example.com/paper",
                pdf_url="https://example.com/paper.pdf",
                status="candidate",
            )
            session.add(paper)
            await session.flush()
            doc = await session.get(WriterDocument, doc_id)
            assert doc is not None
            doc.source_paper_ids_json = [paper.id]
            await session.commit()

        response = await client.get(
            f"/writer/documents/{doc_id}",
            headers=writer_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["source_paper_ids_json"] == [paper.id]
        assert data["source_papers"] == [
            {
                "id": paper.id,
                "title": "Human-readable attached source",
                "authors": ["A. Scholar"],
                "year": 2025,
                "source": "semantic_scholar",
                "source_paper_id": "S2-123",
                "source_url": "https://example.com/paper",
                "pdf_url": "https://example.com/paper.pdf",
                "reference_file_id": None,
            }
        ]

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

    async def test_section_outline_propose_endpoint(
        self,
        client: AsyncClient,
        writer_auth_headers: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        create_resp = await client.post(
            f"/projects/{writer_project['id']}/writer/documents",
            json={"topic": "object tracking", "title": "Tracking Paper", "paper_type": "research"},
            headers=writer_auth_headers,
        )
        doc = create_resp.json()
        doc_id = doc["id"]
        methods_section = next(s for s in doc["sections"] if s["section_type"] == "methods")
        section_id = methods_section["id"]

        response = await client.post(
            f"/writer/documents/{doc_id}/sections/{section_id}/outline/propose",
            headers=writer_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["section_id"] == section_id
        assert r"\subsection{Proposed Method}" in data["outline_text"]

    async def test_section_outline_approve_endpoint(
        self,
        client: AsyncClient,
        writer_auth_headers: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        create_resp = await client.post(
            f"/projects/{writer_project['id']}/writer/documents",
            json={"topic": "object tracking", "title": "Tracking Paper", "paper_type": "research"},
            headers=writer_auth_headers,
        )
        doc = create_resp.json()
        doc_id = doc["id"]
        methods_section = next(s for s in doc["sections"] if s["section_type"] == "methods")
        section_id = methods_section["id"]
        outline = r"\subsection{Proposed Method}"

        response = await client.put(
            f"/writer/documents/{doc_id}/sections/{section_id}/outline",
            json={"outline_text": outline},
            headers=writer_auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["outline_text"] == outline
        assert response.json()["status"] == "awaiting_input"

    async def test_draft_section_endpoint_requires_approved_outline(
        self,
        client: AsyncClient,
        writer_auth_headers: dict[str, str],
        writer_project: dict[str, str],
    ) -> None:
        create_resp = await client.post(
            f"/projects/{writer_project['id']}/writer/documents",
            json={"topic": "object tracking", "title": "Tracking Paper", "paper_type": "research"},
            headers=writer_auth_headers,
        )
        doc = create_resp.json()
        doc_id = doc["id"]
        methods_section = next(s for s in doc["sections"] if s["section_type"] == "methods")
        section_id = methods_section["id"]

        response = await client.post(
            f"/writer/documents/{doc_id}/sections/{section_id}/draft",
            headers=writer_auth_headers,
        )

        assert response.status_code == 422
        assert response.json()["detail"] == "Approve a section outline before drafting."

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
