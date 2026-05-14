"""Writer document service — manages IMRaD writer workspace documents."""

from __future__ import annotations

import io
import json
import logging
import re
import zipfile
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse, urlunparse

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from backend.agents.writer import WriterPaperContext
from backend.agents.writer_section import (
    DEFAULT_IMRAD_PREAMBLE,
    IMRAD_SECTION_DEFAULTS,
    WriterSectionAgent,
    section_questions,
)
from backend.config import get_settings
from backend.db.models import (
    Paper,
    PaperChunk,
    Project,
    ReferenceFile,
    Summary,
    WriterDocument,
    WriterDocumentSource,
    WriterSection,
    WriterSectionVersion,
    generate_identifier,
)
from backend.services.arxiv import ArxivUnavailable, download_pdf
from backend.services.citations import CitationFormatter
from backend.services.document_extraction import (
    DocumentExtractionError,
    PaperDocumentExtractionService,
)
from backend.services.embeddings import EmbeddingService
from backend.services.llm import OpenRouterStructuredOutputService
from backend.services.reference_files import ReferenceFileService
from backend.services.research_utils import cosine_similarity
from backend.services.tavily import ACADEMIC_DOMAINS, TavilySearchService

MAX_SECTION_VERSIONS = 5
WRITER_TAVILY_SOURCE_POOL = 12
WRITER_ARXIV_SOURCE_POOL = 7
WRITER_SOURCE_LIMIT = 7
DRAFT_OUTLINE_REQUIRED_MESSAGE = "Approve a section outline before drafting."
STRUCTURED_METHODS_OUTLINE_REQUIRED_MESSAGE = "Approve a structured Methods outline before drafting."
STRUCTURED_RESULTS_OUTLINE_REQUIRED_MESSAGE = "Approve a structured Results outline before drafting."
ARXIV_ID_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)")
ARXIV_ID_VALUE_RE = re.compile(r"^\d{4}\.\d{4,5}(?:v\d+)?$", re.IGNORECASE)
TODO_PATTERN = re.compile(r"\\todo\{[^}]*\}")
CITE_COMMAND_PATTERN = re.compile(r"(\\cite[a-zA-Z*]*)\{([^}]+)\}")
SOURCE_RANK_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_-]{2,}", re.IGNORECASE)
UUID_LIKE_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
SOURCE_RANKER_SYSTEM_PROMPT = (
    "You rank academic/web source candidates for one section of a research paper. "
    "Keep only candidates that are directly useful for the requested document/section. "
    "Return strict JSON matching the schema; do not invent candidate IDs."
)
SOURCE_RANKER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ranked_candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string"},
                    "relevance_score": {"type": "number"},
                    "keep": {"type": "boolean"},
                    "rationale": {"type": "string"},
                },
                "required": ["candidate_id", "relevance_score", "keep", "rationale"],
                "additionalProperties": False,
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["ranked_candidates", "warnings"],
    "additionalProperties": False,
}
RESEARCH_SECTION_OUTLINES: dict[str, str] = {
    "abstract": (
        "Summarize the research problem, empirical method, key results, and contribution. "
        "Draft this after the main sections are stable."
    ),
    "intro": (
        "Frame the empirical problem and motivation.\n"
        "State the research gap.\n"
        "Define the contribution and research questions.\n"
        "Preview the experimental approach."
    ),
    "related_work": (
        "Organize prior work by method family or problem setting.\n"
        "Compare the most relevant baselines.\n"
        "Identify the gap that motivates this research paper."
    ),
    "methods": "\n".join(
        [
            r"\subsection{Study Design and Experimental Setup}",
            r"\subsection{Datasets, Materials, or Participants}",
            r"\subsection{Proposed Method}",
            r"\subsection{Baselines and Comparators}",
            r"\subsection{Evaluation Metrics}",
            r"\subsection{Implementation Details}",
            r"\subsection{Reproducibility and Limitations}",
        ]
    ),
    "results": "\n".join(
        [
            r"\subsection{Primary Quantitative Findings}",
            r"\subsection{Baseline and Comparator Results}",
            r"\subsection{Ablation or Sensitivity Analysis}",
            r"\subsection{Qualitative Findings and Error Cases}",
            r"\subsection{Efficiency and Runtime Results}",
            r"\subsection{Robustness and Statistical Evidence}",
        ]
    ),
    "discussion": (
        "Interpret the results relative to the research questions.\n"
        "Explain limitations and threats to validity.\n"
        "State practical or scientific implications."
    ),
    "conclusion": (
        "Restate the main finding and contribution.\n"
        "Summarize the evidence supporting the contribution.\n"
        "Identify focused future work."
    ),
}
SURVEY_SECTION_OUTLINES: dict[str, str] = {
    "abstract": (
        "Summarize the survey scope, method taxonomy, evaluation dimensions, main comparative findings, "
        "and implications for future work."
    ),
    "intro": (
        "Introduce the surveyed domain and motivation.\n"
        "Define the scope and research questions.\n"
        "Summarize why a comparative survey is needed.\n"
        "Preview the survey organization."
    ),
    "related_work": (
        "Position this survey against prior surveys and benchmark papers.\n"
        "Explain what earlier reviews covered.\n"
        "Identify the coverage gap addressed by this survey."
    ),
    "methods": "\n".join(
        [
            r"\subsection{Survey Scope and Research Questions}",
            r"\subsection{Literature Search and Selection Criteria}",
            r"\subsection{Tracking Method Taxonomy}",
            r"\subsection{Benchmark and Dataset Coverage}",
            r"\subsection{Evaluation Dimensions}",
            r"\subsection{Comparative Synthesis Procedure}",
            r"\subsection{Limitations of the Review Methodology}",
        ]
    ),
    "results": "\n".join(
        [
            r"\subsection{Comparative Findings by Method Family}",
            r"\subsection{Performance Under High-Speed Conditions}",
            r"\subsection{Benchmark and Dataset Trends}",
            r"\subsection{Accuracy, Robustness, and Latency Trade-offs}",
            r"\subsection{Domain-Specific Evidence}",
            r"\subsection{Key Result Patterns and Gaps}",
        ]
    ),
    "discussion": (
        "Interpret cross-method trends and unresolved challenges.\n"
        "Discuss limitations of the surveyed evidence.\n"
        "Explain implications for deployment and future research."
    ),
    "conclusion": (
        "Summarize the main survey conclusions.\n"
        "Restate the practical takeaways by method family.\n"
        "Identify open problems and future directions."
    ),
}
logger = logging.getLogger(__name__)


class StructuredSourceRankerClient(Protocol):
    """Minimal structured-output surface needed by the writer source ranker."""

    def is_configured(self) -> bool:
        """Return whether live source ranking can run."""
        ...

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        max_tokens: int = 1_024,
        feature: str = "structured_output",
    ) -> dict[str, Any]:
        """Return a structured JSON payload."""
        ...


class WriterDocumentNotFoundError(LookupError):
    """Raised when a writer document is not found."""


class WriterSectionNotFoundError(LookupError):
    """Raised when a writer section is not found."""


class WriterDocumentPermissionError(PermissionError):
    """Raised when a user is not authorized to access a writer document."""


@dataclass(frozen=True)
class AssembleResult:
    """Assembled LaTeX + BibTeX output for a complete document."""

    tex: str
    bib: str
    unresolved_todo_count: int
    warnings: list[str]


class WriterDocumentService:
    """Create and manage IMRaD writer documents."""

    def __init__(
        self,
        *,
        section_agent: WriterSectionAgent | None = None,
        extraction_service: PaperDocumentExtractionService | None = None,
        embedding_service: EmbeddingService | None = None,
        citation_formatter: CitationFormatter | None = None,
        reference_file_service: ReferenceFileService | None = None,
        tavily_service: TavilySearchService | None = None,
        source_ranker_client: StructuredSourceRankerClient | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        self.section_agent = section_agent or WriterSectionAgent()
        self.extraction_service = extraction_service or PaperDocumentExtractionService()
        self.embedding_service = embedding_service or EmbeddingService()
        self.citation_formatter = citation_formatter or CitationFormatter()
        self.reference_file_service = reference_file_service or ReferenceFileService()
        self.tavily_service = tavily_service or TavilySearchService()
        self.source_ranker_client = source_ranker_client
        if self.source_ranker_client is None and settings.xiaomi_mimo_api_key:
            self.source_ranker_client = OpenRouterStructuredOutputService(
                api_key=settings.xiaomi_mimo_api_key,
                base_url=settings.xiaomi_mimo_base_url,
                model=settings.writer_source_ranker_model,
                http_client=http_client,
            )
        self.http_client = http_client

    async def create_document(
        self,
        *,
        session: AsyncSession,
        user_id: str | None = None,
        project_id: str | None = None,
        title: str,
        topic: str,
        thesis: str | None,
        paper_type: str = "imrad",
        citation_style: str = "ieee",
    ) -> WriterDocument:
        owner_id = user_id
        if project_id is not None:
            project = await session.get(Project, project_id)
            if project is None:
                raise WriterDocumentNotFoundError(f"Project '{project_id}' not found.")
            if owner_id is not None and project.user_id != owner_id:
                raise WriterDocumentPermissionError("Access denied.")
            owner_id = project.user_id
        if owner_id is None:
            raise WriterDocumentPermissionError("A writer document owner is required.")

        doc = WriterDocument(
            user_id=owner_id,
            project_id=project_id,
            title=title,
            topic=topic,
            thesis=thesis,
            paper_type=paper_type,
            citation_style=citation_style,
            preamble=DEFAULT_IMRAD_PREAMBLE,
            source_paper_ids_json=[],
            status="outline",
        )
        session.add(doc)
        await session.flush()

        for defaults in IMRAD_SECTION_DEFAULTS:
            section = WriterSection(
                writer_document_id=doc.id,
                section_type=defaults["section_type"],
                order_index=defaults["order_index"],
                title=defaults["title"],
                user_inputs_json={},
                low_confidence_spans_json=[],
                cited_paper_ids_json=[],
                status="planned",
            )
            session.add(section)

        doc_id = doc.id
        await session.commit()
        result = await session.execute(
            select(WriterDocument)
            .options(
                selectinload(WriterDocument.sections),
                selectinload(WriterDocument.project),
                selectinload(WriterDocument.sources).selectinload(WriterDocumentSource.paper),
            )
            .where(WriterDocument.id == doc_id)
        )
        return result.scalar_one()

    async def get_document(
        self,
        *,
        session: AsyncSession,
        document_id: str,
        user_id: str,
    ) -> WriterDocument:
        result = await session.execute(
            select(WriterDocument)
            .options(
                selectinload(WriterDocument.sections),
                selectinload(WriterDocument.project),
                selectinload(WriterDocument.sources).selectinload(WriterDocumentSource.paper),
            )
            .where(WriterDocument.id == document_id)
        )
        doc = result.scalar_one_or_none()
        if doc is None:
            raise WriterDocumentNotFoundError(f"Writer document '{document_id}' not found.")
        if doc.user_id != user_id:
            raise WriterDocumentPermissionError("Access denied.")
        return doc

    async def list_documents(
        self,
        *,
        session: AsyncSession,
        user_id: str | None = None,
        project_id: str | None = None,
    ) -> list[WriterDocument]:
        if project_id is not None:
            project = await session.get(Project, project_id)
            if project is None:
                raise WriterDocumentNotFoundError(f"Project '{project_id}' not found.")
            if user_id is not None and project.user_id != user_id:
                raise WriterDocumentPermissionError("Access denied.")
            owner_id = project.user_id
        elif user_id is not None:
            owner_id = user_id
        else:
            raise WriterDocumentPermissionError("A writer document owner is required.")

        statement = (
            select(WriterDocument)
            .options(selectinload(WriterDocument.sections))
            .where(WriterDocument.user_id == owner_id)
            .order_by(WriterDocument.created_at.desc())
        )
        if project_id is not None:
            statement = statement.where(WriterDocument.project_id == project_id)

        result = await session.execute(
            statement
        )
        return list(result.scalars().all())

    async def update_document(
        self,
        *,
        session: AsyncSession,
        document_id: str,
        user_id: str,
        title: str | None = None,
        thesis: str | None = None,
        preamble: str | None = None,
    ) -> WriterDocument:
        doc = await self.get_document(session=session, document_id=document_id, user_id=user_id)
        if title is not None:
            doc.title = title
        if thesis is not None:
            doc.thesis = thesis
        if preamble is not None:
            doc.preamble = preamble
        await session.commit()
        return await self.get_document(session=session, document_id=document_id, user_id=user_id)

    async def delete_document(
        self,
        *,
        session: AsyncSession,
        document_id: str,
        user_id: str,
    ) -> None:
        doc = await self.get_document(session=session, document_id=document_id, user_id=user_id)
        await session.delete(doc)
        await session.commit()

    async def propose_outline(
        self,
        *,
        session: AsyncSession,
        document_id: str,
        user_id: str,
    ) -> dict[str, str]:
        doc = await self.get_document(session=session, document_id=document_id, user_id=user_id)
        outline: dict[str, str] = {}
        for section in doc.sections:
            outline[section.id] = self._default_outline_text(
                paper_type=doc.paper_type,
                section_type=section.section_type,
                topic=doc.topic,
                thesis=doc.thesis,
            )
        return outline

    async def propose_section_outline(
        self,
        *,
        session: AsyncSession,
        section_id: str,
        user_id: str,
    ) -> tuple[WriterSection, str]:
        section, doc = await self._load_section_with_doc(
            session=session,
            section_id=section_id,
            user_id=user_id,
        )
        outline = self._default_outline_text(
            paper_type=doc.paper_type,
            section_type=section.section_type,
            topic=doc.topic,
            thesis=doc.thesis,
        )
        return section, outline

    async def approve_section_outline(
        self,
        *,
        session: AsyncSession,
        section_id: str,
        user_id: str,
        outline_text: str,
    ) -> WriterSection:
        normalized_outline = outline_text.strip()
        if not normalized_outline:
            raise ValueError("Section outline cannot be empty.")
        section, doc = await self._load_section_with_doc(
            session=session,
            section_id=section_id,
            user_id=user_id,
        )
        section.outline_text = normalized_outline
        section.status = "awaiting_input"
        doc.status = "drafting"
        await session.commit()
        await session.refresh(section)
        return section

    async def apply_outline(
        self,
        *,
        session: AsyncSession,
        document_id: str,
        user_id: str,
        outline_by_section: dict[str, str],
    ) -> WriterDocument:
        doc = await self.get_document(session=session, document_id=document_id, user_id=user_id)
        for section in doc.sections:
            if section.id in outline_by_section:
                section.outline_text = outline_by_section[section.id]
                section.status = "awaiting_input"
        doc.status = "drafting"
        await session.commit()
        return await self.get_document(session=session, document_id=document_id, user_id=user_id)

    async def get_section_questions(
        self,
        *,
        session: AsyncSession,
        section_id: str,
        user_id: str,
    ) -> tuple[WriterSection, list[str]]:
        section, _ = await self._load_section_with_doc(
            session=session, section_id=section_id, user_id=user_id
        )
        return section, section_questions(section.section_type)

    async def submit_section_inputs(
        self,
        *,
        session: AsyncSession,
        section_id: str,
        user_id: str,
        answers: dict[str, str],
    ) -> WriterSection:
        section, _ = await self._load_section_with_doc(
            session=session, section_id=section_id, user_id=user_id
        )
        section.user_inputs_json = answers
        section.status = "awaiting_input"
        await session.commit()
        await session.refresh(section)
        return section

    async def draft_section(
        self,
        *,
        session: AsyncSession,
        section_id: str,
        user_id: str,
    ) -> tuple[WriterSection, list[str]]:
        section, doc = await self._load_section_with_doc(
            session=session, section_id=section_id, user_id=user_id
        )
        if not (section.outline_text or "").strip():
            raise ValueError(DRAFT_OUTLINE_REQUIRED_MESSAGE)
        if self._requires_structured_methods_outline(doc=doc, section=section):
            raise ValueError(STRUCTURED_METHODS_OUTLINE_REQUIRED_MESSAGE)
        if self._requires_structured_results_outline(doc=doc, section=section):
            raise ValueError(STRUCTURED_RESULTS_OUTLINE_REQUIRED_MESSAGE)

        papers = await self._load_document_source_papers(session=session, doc=doc)

        # Auto-search on every draft to supplement attached sources.
        auto_papers, auto_warnings = await self._auto_fetch_source_papers(
            session=session,
            doc=doc,
            section=section,
            existing_papers=papers,
        )
        papers = [*papers, *auto_papers]

        paper_contexts = await self._build_paper_contexts(
            session=session,
            papers=papers,
            instruction=f"Write the {section.section_type} section: {section.title}",
        )

        draft_result = await self.section_agent.draft_section(
            section_id=section_id,
            paper_type=doc.paper_type,
            section_type=section.section_type,
            title=section.title,
            outline_text=section.outline_text,
            user_inputs=dict(section.user_inputs_json or {}),
            paper_contexts=paper_contexts,
            citation_style=doc.citation_style,
        )

        if section.draft_latex:
            await self._snapshot_section(session=session, section=section)

        section.draft_latex = draft_result.draft_latex
        section.low_confidence_spans_json = [
            {
                "section_id": span.section_id,
                "text": span.text,
                "reason": span.reason,
                "suggested_query": span.suggested_query,
                "char_offset": span.char_offset,
            }
            for span in draft_result.low_confidence_spans
        ]
        section.cited_paper_ids_json = draft_result.cited_paper_ids
        section.status = "drafted"
        await session.commit()
        await session.refresh(section)
        return section, [*auto_warnings, *draft_result.warnings]

    async def save_section_edit(
        self,
        *,
        session: AsyncSession,
        section_id: str,
        user_id: str,
        draft_latex: str,
    ) -> WriterSection:
        section, _ = await self._load_section_with_doc(
            session=session, section_id=section_id, user_id=user_id
        )
        if section.draft_latex:
            await self._snapshot_section(session=session, section=section)
        section.draft_latex = draft_latex
        section.status = "user_edited"
        await session.commit()
        await session.refresh(section)
        return section

    async def get_section_versions(
        self,
        *,
        session: AsyncSession,
        section_id: str,
        user_id: str,
    ) -> list[WriterSectionVersion]:
        section, _ = await self._load_section_with_doc(
            session=session, section_id=section_id, user_id=user_id
        )
        result = await session.execute(
            select(WriterSectionVersion)
            .where(WriterSectionVersion.writer_section_id == section.id)
            .order_by(WriterSectionVersion.created_at.desc())
        )
        return list(result.scalars().all())

    async def revert_to_version(
        self,
        *,
        session: AsyncSession,
        section_id: str,
        version_id: str,
        user_id: str,
    ) -> WriterSection:
        section, _ = await self._load_section_with_doc(
            session=session, section_id=section_id, user_id=user_id
        )
        version = await session.get(WriterSectionVersion, version_id)
        if version is None or version.writer_section_id != section_id:
            raise WriterSectionNotFoundError(f"Version '{version_id}' not found.")

        if section.draft_latex:
            await self._snapshot_section(session=session, section=section)

        section.draft_latex = version.draft_latex
        section.status = "user_edited"
        await session.commit()
        await session.refresh(section)
        return section

    async def suggest_sources(
        self,
        *,
        session: AsyncSession,
        document_id: str,
        user_id: str,
        query: str,
        section_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        doc = await self.get_document(session=session, document_id=document_id, user_id=user_id)
        section: WriterSection | None = None
        if section_id:
            section, section_doc = await self._load_section_with_doc(
                session=session,
                section_id=section_id,
                user_id=user_id,
            )
            if section_doc.id != doc.id:
                raise WriterSectionNotFoundError(f"Section '{section_id}' not found.")

        attached_papers = await self._load_document_source_papers(session=session, doc=doc)

        candidates: list[dict[str, Any]] = []
        warnings: list[str] = []

        try:
            arxiv_papers = await self._fetch_arxiv_candidates(
                query, limit=WRITER_ARXIV_SOURCE_POOL
            )
            for p in arxiv_papers:
                candidates.append({**p, "pdf_available": bool(p.get("pdf_url"))})
        except ArxivUnavailable as err:
            logger.info("arXiv skipped (transient): %s", err)
        except Exception as err:
            msg = str(err) if str(err) else type(err).__name__
            warnings.append(f"arXiv unavailable: {msg}")

        try:
            tavily_response = await self.tavily_service.search(
                query,
                include_domains=ACADEMIC_DOMAINS,
                max_results=WRITER_TAVILY_SOURCE_POOL,
            )
            warnings.extend(tavily_response.warnings)
            for result in tavily_response.results:
                candidates.append(self._candidate_from_tavily_result(result, source="tavily"))
        except Exception as err:
            warnings.append(f"Tavily search failed: {err}")

        ranked_candidates, ranker_warnings = await self._rank_source_candidates(
            doc=doc,
            section=section,
            raw_candidates=candidates,
            attached_papers=attached_papers,
            query=query,
        )
        warnings.extend(ranker_warnings)
        return [self._public_source_candidate(candidate) for candidate in ranked_candidates], warnings

    async def attach_source(
        self,
        *,
        session: AsyncSession,
        document_id: str,
        user_id: str,
        candidate: dict[str, Any],
    ) -> tuple[str | None, bool, str]:
        doc = await self.get_document(session=session, document_id=document_id, user_id=user_id)

        source_paper_id = candidate.get("source_paper_id")
        source_url = candidate.get("source_url")
        existing_conditions = []
        if source_paper_id:
            existing_conditions.append(Paper.source_paper_id == source_paper_id)
        if source_url:
            existing_conditions.append(Paper.source_url == source_url)
        if existing_conditions:
            existing_result = await session.execute(
                select(Paper)
                .where(
                    self._paper_access_filter(doc),
                    or_(*existing_conditions),
                )
                .limit(1)
            )
            existing_paper = existing_result.scalar_one_or_none()
            if existing_paper is not None:
                await self._attach_paper_to_document(
                    session=session,
                    doc=doc,
                    paper=existing_paper,
                    source_origin=str(candidate.get("source") or "existing"),
                )
                return existing_paper.id, False, "Source already attached."

        pdf_url = candidate.get("pdf_url")
        arxiv_id = candidate.get("arxiv_id") or self._extract_arxiv_id(
            candidate.get("source_url") or ""
        )

        pdf_fetched = False
        pdf_bytes: bytes | None = None
        fetch_url = pdf_url or (f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else None)

        if fetch_url:
            try:
                pdf_bytes = await download_pdf(fetch_url, http_client=self.http_client)
                pdf_fetched = True
            except RuntimeError:
                pass

        if pdf_fetched and pdf_bytes:
            project = await session.get(Project, doc.project_id) if doc.project_id else None
            filename = f"{arxiv_id or 'paper'}.pdf"
            try:
                ref_file = await self.reference_file_service.create_reference_file(
                    session=session,
                    project=project,
                    user_id=doc.user_id,
                    filename=filename,
                    content_type="application/pdf",
                    content=pdf_bytes,
                )
                paper_id = ref_file.paper.id if ref_file.paper else None
                if paper_id:
                    paper = await session.get(Paper, paper_id)
                    if paper is not None:
                        await self._attach_paper_to_document(
                            session=session,
                            doc=doc,
                            paper=paper,
                            source_origin=str(candidate.get("source") or "upload"),
                        )
                return paper_id, False, "Source attached and PDF fetched."
            except Exception:
                pass

        # PDF unavailable — create a metadata-only Paper so drafting still works
        title = str(candidate.get("title") or "Untitled")
        authors = candidate.get("authors") or []
        year = candidate.get("year")
        abstract = candidate.get("abstract")
        paper = Paper(
            id=generate_identifier(),
            user_id=doc.user_id,
            project_id=None,
            title=title,
            authors=list(authors),
            year=int(year) if year else None,
            abstract=str(abstract) if abstract else None,
            source=str(candidate.get("source") or "writer_attach"),
            source_paper_id=source_paper_id,
            source_url=source_url,
            pdf_url=fetch_url,
            status="candidate",
        )
        session.add(paper)
        await session.flush()
        await self._attach_paper_to_document(
            session=session,
            doc=doc,
            paper=paper,
            source_origin=str(candidate.get("source") or "writer_attach"),
        )
        return paper.id, False, "Source attached (metadata only — PDF unavailable)."

    async def remove_source(
        self,
        *,
        session: AsyncSession,
        document_id: str,
        user_id: str,
        paper_id: str,
    ) -> None:
        doc = await self.get_document(session=session, document_id=document_id, user_id=user_id)
        rows = await session.execute(
            select(WriterDocumentSource).where(
                WriterDocumentSource.writer_document_id == doc.id,
                WriterDocumentSource.paper_id == paper_id,
            )
        )
        for row in rows.scalars().all():
            await session.delete(row)
        doc.source_paper_ids_json = [p for p in doc.source_paper_ids_json if p != paper_id]
        await session.commit()

    def get_qa_report(self, document: WriterDocument) -> dict[str, Any]:
        todos: list[dict[str, Any]] = []
        for section in document.sections:
            for span in section.low_confidence_spans_json:
                todos.append({**span, "section_title": section.title})
        return {"unresolved_todos": todos, "total_count": len(todos)}

    async def assemble(
        self,
        *,
        session: AsyncSession,
        document_id: str,
        user_id: str,
    ) -> AssembleResult:
        doc = await self.get_document(session=session, document_id=document_id, user_id=user_id)
        cited_ids_from_drafts = self._extract_cited_paper_ids_from_sections(doc.sections)
        source_paper_ids = await self._document_source_paper_ids(session=session, doc=doc)
        paper_ids = self._ordered_unique([*source_paper_ids, *cited_ids_from_drafts])
        papers = await self._load_papers_by_ids(session=session, paper_ids=paper_ids)
        loaded_paper_ids = {paper.id for paper in papers}
        missing_citation_ids = [
            paper_id
            for paper_id in cited_ids_from_drafts
            if paper_id not in loaded_paper_ids and UUID_LIKE_PATTERN.match(paper_id)
        ]
        citation_bundle = self.citation_formatter.prepare_bundle(
            papers=papers, reference_style=doc.citation_style
        )

        preamble = doc.preamble or DEFAULT_IMRAD_PREAMBLE
        section_bodies: list[str] = []
        todo_count = 0
        warnings: list[str] = []

        for section in sorted(doc.sections, key=lambda s: s.order_index):
            if section.draft_latex:
                body = self._substitute_citation_keys(
                    section.draft_latex, citation_bundle.citation_keys_by_paper_id
                )
                todo_count += len(TODO_PATTERN.findall(body))
                section_bodies.append(body)
            else:
                warnings.append(f"Section '{section.title}' has no draft yet.")

        for missing_id in missing_citation_ids:
            warnings.append(
                f"Citation '{missing_id}' has no matching writer source; no reference was generated."
            )

        bib_entries = list(citation_bundle.bibtex_entries_by_paper_id.values())
        bib_text = "\n\n".join(bib_entries)

        tex = (
            preamble
            + "\n\n"
            + "\n\n".join(section_bodies)
            + "\n\n\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n"
        )

        doc.bib_text = bib_text
        for paper in papers:
            await self._attach_paper_to_document(
                session=session,
                doc=doc,
                paper=paper,
                source_origin="draft_citation",
                commit=False,
            )
        doc.source_paper_ids_json = self._ordered_unique([paper.id for paper in papers])
        doc.status = "ready"
        await session.commit()

        return AssembleResult(tex=tex, bib=bib_text, unresolved_todo_count=todo_count, warnings=warnings)

    async def export_bundle(
        self,
        *,
        session: AsyncSession,
        document_id: str,
        user_id: str,
    ) -> bytes:
        result = await self.assemble(session=session, document_id=document_id, user_id=user_id)
        doc = await self.get_document(session=session, document_id=document_id, user_id=user_id)
        qa_report = self.get_qa_report(doc)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("paper.tex", result.tex)
            zf.writestr("references.bib", result.bib)
            zf.writestr("qa_report.json", json.dumps(qa_report, indent=2))
        doc.status = "exported"
        await session.commit()
        return buffer.getvalue()

    async def _load_section_with_doc(
        self,
        *,
        session: AsyncSession,
        section_id: str,
        user_id: str,
    ) -> tuple[WriterSection, WriterDocument]:
        result = await session.execute(
            select(WriterSection)
            .options(
                selectinload(WriterSection.document).selectinload(WriterDocument.project),
                selectinload(WriterSection.document).selectinload(WriterDocument.sections),
                selectinload(WriterSection.document)
                .selectinload(WriterDocument.sources)
                .selectinload(WriterDocumentSource.paper),
            )
            .where(WriterSection.id == section_id)
        )
        section = result.scalar_one_or_none()
        if section is None:
            raise WriterSectionNotFoundError(f"Section '{section_id}' not found.")
        doc = section.document
        if doc.user_id != user_id:
            raise WriterDocumentPermissionError("Access denied.")
        return section, doc

    async def _snapshot_section(
        self,
        *,
        session: AsyncSession,
        section: WriterSection,
    ) -> None:
        if not section.draft_latex:
            return
        version = WriterSectionVersion(
            writer_section_id=section.id,
            draft_latex=section.draft_latex,
        )
        session.add(version)
        await session.flush()
        existing = await session.execute(
            select(WriterSectionVersion)
            .where(WriterSectionVersion.writer_section_id == section.id)
            .order_by(WriterSectionVersion.created_at.desc())
        )
        all_versions = list(existing.scalars().all())
        if len(all_versions) > MAX_SECTION_VERSIONS:
            for old in all_versions[MAX_SECTION_VERSIONS:]:
                await session.delete(old)

    async def _document_source_paper_ids(
        self,
        *,
        session: AsyncSession,
        doc: WriterDocument,
    ) -> list[str]:
        result = await session.execute(
            select(WriterDocumentSource.paper_id)
            .where(
                WriterDocumentSource.writer_document_id == doc.id,
                WriterDocumentSource.paper_id.is_not(None),
            )
            .order_by(WriterDocumentSource.order_index.asc())
        )
        source_ids = [paper_id for paper_id in result.scalars().all() if paper_id]
        doc.source_paper_ids_json = self._ordered_unique(
            [*(doc.source_paper_ids_json or []), *source_ids]
        )
        return doc.source_paper_ids_json

    async def _load_document_source_papers(
        self,
        *,
        session: AsyncSession,
        doc: WriterDocument,
    ) -> list[Paper]:
        paper_ids = await self._document_source_paper_ids(session=session, doc=doc)
        return await self._load_papers_by_ids(session=session, paper_ids=paper_ids)

    async def _load_papers_by_ids(
        self,
        *,
        session: AsyncSession,
        paper_ids: list[str],
    ) -> list[Paper]:
        if not paper_ids:
            return []
        result = await session.execute(
            select(Paper)
            .options(selectinload(Paper.summary))
            .where(Paper.id.in_(paper_ids))
        )
        papers_by_id = {p.id: p for p in result.scalars().all()}
        return [papers_by_id[pid] for pid in paper_ids if pid in papers_by_id]

    def _paper_access_filter(self, doc: WriterDocument) -> ColumnElement[bool]:
        conditions = [Paper.user_id == doc.user_id]
        if doc.project_id is not None:
            conditions.append(Paper.project_id == doc.project_id)
        return or_(*conditions)

    async def _attach_paper_to_document(
        self,
        *,
        session: AsyncSession,
        doc: WriterDocument,
        paper: Paper,
        source_origin: str,
        notes: str | None = None,
        commit: bool = True,
    ) -> None:
        result = await session.execute(
            select(WriterDocumentSource).where(
                WriterDocumentSource.writer_document_id == doc.id,
                WriterDocumentSource.paper_id == paper.id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            order_index = len(await self._document_source_paper_ids(session=session, doc=doc))
            session.add(
                WriterDocumentSource(
                    writer_document_id=doc.id,
                    paper_id=paper.id,
                    source_origin=source_origin,
                    notes=notes,
                    order_index=order_index,
                )
            )
        elif notes and not existing.notes:
            existing.notes = notes

        if paper.id not in doc.source_paper_ids_json:
            doc.source_paper_ids_json = [*doc.source_paper_ids_json, paper.id]
        if commit:
            await session.commit()

    async def _can_use_paper(
        self,
        *,
        session: AsyncSession,
        doc: WriterDocument,
        user_id: str,
        paper: Paper,
    ) -> bool:
        if paper.user_id == user_id and paper.project_id is None:
            return True
        if paper.project_id is not None and paper.project_id == doc.project_id:
            project = await session.get(Project, paper.project_id)
            return project is not None and project.user_id == user_id
        return False

    async def _copy_project_paper_for_document(
        self,
        *,
        session: AsyncSession,
        source_paper: Paper,
        user_id: str,
    ) -> Paper:
        existing_result = await session.execute(
            select(Paper)
            .options(selectinload(Paper.summary), selectinload(Paper.chunks))
            .where(
                Paper.user_id == user_id,
                Paper.project_id.is_(None),
                Paper.source == "project_import",
                Paper.source_paper_id == source_paper.id,
            )
            .limit(1)
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            return existing

        imported = Paper(
            id=generate_identifier(),
            user_id=user_id,
            project_id=None,
            title=source_paper.title,
            authors=list(source_paper.authors),
            year=source_paper.year,
            abstract=source_paper.abstract,
            doi=source_paper.doi,
            source="project_import",
            source_paper_id=source_paper.id,
            source_url=source_paper.source_url,
            pdf_url=source_paper.pdf_url,
            citation_count=source_paper.citation_count,
            reference_count=source_paper.reference_count,
            status=source_paper.status,
            relevance_score=source_paper.relevance_score,
        )
        session.add(imported)
        await session.flush()

        if source_paper.summary is not None:
            session.add(
                Summary(
                    paper_id=imported.id,
                    problem=source_paper.summary.problem,
                    method=source_paper.summary.method,
                    result=source_paper.summary.result,
                    relevance_to_topic=source_paper.summary.relevance_to_topic,
                    has_error=source_paper.summary.has_error,
                    error_message=source_paper.summary.error_message,
                )
            )

        for chunk in source_paper.chunks:
            session.add(
                PaperChunk(
                    paper_id=imported.id,
                    chunk_index=chunk.chunk_index,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    section_title=chunk.section_title,
                    content=chunk.content,
                    embedding_json=list(chunk.embedding_json),
                )
            )

        await session.flush()
        return imported

    async def _build_paper_contexts(
        self,
        *,
        session: AsyncSession,
        papers: list[Paper],
        instruction: str,
    ) -> list[WriterPaperContext]:
        try:
            embeddings = await self.embedding_service.embed_texts([instruction.strip()])
            instruction_vec = embeddings[0] if embeddings else []
        except Exception:
            instruction_vec = self.embedding_service.embed_texts_locally([instruction.strip()])[0]

        contexts: list[WriterPaperContext] = []
        for paper in papers:
            chunks = await self._fetch_top_chunks(
                session=session, paper=paper, instruction_vec=instruction_vec
            )
            summary = paper.summary
            contexts.append(
                WriterPaperContext(
                    paper_id=paper.id,
                    title=paper.title,
                    authors=list(paper.authors),
                    year=paper.year,
                    abstract=paper.abstract,
                    problem=summary.problem if summary else None,
                    method=summary.method if summary else None,
                    result=summary.result if summary else None,
                    relevance_to_topic=summary.relevance_to_topic if summary else None,
                    evidence_snippets=chunks,
                    metadata_warnings=[],
                )
            )
        return contexts

    async def _fetch_top_chunks(
        self,
        *,
        session: AsyncSession,
        paper: Paper,
        instruction_vec: list[float],
        top_k: int = 7,
    ) -> list[str]:
        from backend.db.models import PaperChunk

        result = await session.execute(
            select(PaperChunk).where(PaperChunk.paper_id == paper.id)
        )
        chunks = list(result.scalars().all())
        if not chunks:
            if paper.pdf_url:
                try:
                    await self.extraction_service.ensure_document_chunks(session=session, paper=paper)
                    result2 = await session.execute(
                        select(PaperChunk).where(PaperChunk.paper_id == paper.id)
                    )
                    chunks = list(result2.scalars().all())
                except DocumentExtractionError:
                    pass

        if not chunks or not instruction_vec:
            return []

        ranked = []
        for chunk in chunks:
            vec = [float(v) for v in chunk.embedding_json]
            if not vec:
                continue
            try:
                sim = cosine_similarity(instruction_vec, vec)
                ranked.append((sim, chunk.content[:420]))
            except ValueError:
                continue

        ranked.sort(key=lambda x: x[0], reverse=True)
        return [text for _, text in ranked[:top_k]]

    async def _auto_fetch_source_papers(
        self,
        *,
        session: AsyncSession,
        doc: WriterDocument,
        section: WriterSection,
        existing_papers: list[Paper],
    ) -> tuple[list[Paper], list[str]]:
        """Auto-fetch draft sources, falling back to arXiv when Tavily has no candidates."""

        tavily_papers, tavily_warnings = await self._auto_fetch_tavily_papers(
            session=session,
            doc=doc,
            section=section,
            existing_papers=existing_papers,
        )
        if tavily_papers or existing_papers:
            return tavily_papers, []

        arxiv_papers, arxiv_warnings = await self._auto_fetch_arxiv_papers(
            session=session,
            doc=doc,
            section=section,
            existing_papers=existing_papers,
        )
        if arxiv_papers:
            return arxiv_papers, []

        warnings = [*arxiv_warnings, *tavily_warnings]
        if not warnings:
            warnings.append("Auto-search found no usable sources for this section.")
        return [], warnings

    async def _auto_fetch_tavily_papers(
        self,
        *,
        session: AsyncSession,
        doc: WriterDocument,
        section: WriterSection,
        existing_papers: list[Paper],
    ) -> tuple[list[Paper], list[str]]:
        """Auto-search Tavily on every draft and create metadata-only Papers for new results."""
        query = self._build_section_source_query(doc=doc, section=section)

        try:
            tavily_response = await self.tavily_service.search(
                query,
                include_domains=ACADEMIC_DOMAINS,
                max_results=WRITER_TAVILY_SOURCE_POOL,
            )
        except Exception as err:
            return [], [f"Tavily search failed: {err}"]

        raw_candidates = [
            self._candidate_from_tavily_result(result, source="tavily_auto")
            for result in tavily_response.results
        ]
        ranked_candidates, ranker_warnings = await self._rank_source_candidates(
            doc=doc,
            section=section,
            raw_candidates=raw_candidates,
            attached_papers=existing_papers,
            query=query,
        )
        papers = await self._persist_auto_source_candidates(
            session=session,
            doc=doc,
            ranked_candidates=ranked_candidates,
        )
        warnings = [*tavily_response.warnings, *ranker_warnings]
        return papers, ([] if papers else warnings)

    async def _auto_fetch_arxiv_papers(
        self,
        *,
        session: AsyncSession,
        doc: WriterDocument,
        section: WriterSection,
        existing_papers: list[Paper],
    ) -> tuple[list[Paper], list[str]]:
        """Auto-search arXiv when Tavily cannot provide draft sources."""

        query = self._build_section_source_query(doc=doc, section=section)
        try:
            raw_candidates = await self._fetch_arxiv_candidates(
                query,
                limit=WRITER_ARXIV_SOURCE_POOL,
            )
        except ArxivUnavailable as err:
            logger.info("arXiv skipped (transient) in auto-fetch: %s", err)
            return [], []
        except Exception as err:
            msg = str(err) if str(err) else type(err).__name__
            return [], [f"arXiv unavailable: {msg}"]

        ranked_candidates, ranker_warnings = await self._rank_source_candidates(
            doc=doc,
            section=section,
            raw_candidates=raw_candidates,
            attached_papers=existing_papers,
            query=query,
        )
        papers = await self._persist_auto_source_candidates(
            session=session,
            doc=doc,
            ranked_candidates=ranked_candidates,
        )
        return papers, ([] if papers else ranker_warnings)

    async def _persist_auto_source_candidates(
        self,
        *,
        session: AsyncSession,
        doc: WriterDocument,
        ranked_candidates: list[dict[str, Any]],
    ) -> list[Paper]:
        """Persist ranked auto-source candidates as project papers."""

        new_papers: list[Paper] = []
        for candidate in ranked_candidates:
            source_url = self._clean_optional_string(candidate.get("source_url"))
            source_paper_id = self._clean_optional_string(candidate.get("source_paper_id"))
            paper = Paper(
                id=generate_identifier(),
                user_id=doc.user_id,
                project_id=None,
                title=str(candidate.get("title") or "Untitled"),
                authors=list(candidate.get("authors") or []),
                year=int(candidate["year"]) if candidate.get("year") else None,
                source=str(candidate.get("source") or "tavily_auto"),
                source_paper_id=source_paper_id,
                source_url=source_url,
                pdf_url=self._clean_optional_string(candidate.get("pdf_url")),
                abstract=self._clean_optional_string(candidate.get("abstract")),
                status="candidate",
            )
            session.add(paper)
            new_papers.append(paper)

        if not new_papers:
            return []

        new_ids = [p.id for p in new_papers]
        await session.flush()
        for paper in new_papers:
            await self._attach_paper_to_document(
                session=session,
                doc=doc,
                paper=paper,
                source_origin=str(paper.source or "auto_search"),
                commit=False,
            )

        # Re-query with selectinload so Paper.summary is eagerly loaded (avoids MissingGreenlet)
        reloaded = await session.execute(
            select(Paper).options(selectinload(Paper.summary)).where(Paper.id.in_(new_ids))
        )
        papers_by_id = {paper.id: paper for paper in reloaded.scalars().all()}
        return [papers_by_id[paper_id] for paper_id in new_ids if paper_id in papers_by_id]

    async def _rank_source_candidates(
        self,
        *,
        doc: WriterDocument,
        section: WriterSection | None,
        raw_candidates: list[dict[str, Any]],
        attached_papers: list[Paper],
        query: str,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        candidates = self._normalize_source_candidates(
            raw_candidates=raw_candidates,
            attached_papers=attached_papers,
        )
        if not candidates:
            return [], []

        local_ranked = self._local_rank_source_candidates(
            doc=doc,
            section=section,
            candidates=candidates,
            query=query,
        )
        ranker = self.source_ranker_client
        if ranker is None or not ranker.is_configured():
            return local_ranked[:WRITER_SOURCE_LIMIT], []

        try:
            payload = await ranker.generate_json(
                system_prompt=SOURCE_RANKER_SYSTEM_PROMPT,
                user_prompt=json.dumps(
                    self._source_ranker_prompt_payload(
                        doc=doc,
                        section=section,
                        candidates=candidates,
                        query=query,
                    )
                ),
                schema=SOURCE_RANKER_SCHEMA,
                max_tokens=1_800,
                feature="writer_source_ranker",
            )
        except Exception:
            return local_ranked[:WRITER_SOURCE_LIMIT], [
                "Source ranker failed; used local ranking."
            ]

        ranked_candidates, warnings = self._ranked_candidates_from_provider_payload(
            payload=payload,
            candidates=candidates,
            local_ranked=local_ranked,
        )
        return ranked_candidates[:WRITER_SOURCE_LIMIT], warnings

    def _normalize_source_candidates(
        self,
        *,
        raw_candidates: list[dict[str, Any]],
        attached_papers: list[Paper],
    ) -> list[dict[str, Any]]:
        attached_keys: set[str] = set()
        for paper in attached_papers:
            attached_keys.update(
                self._source_identity_keys(
                    {
                        "source_paper_id": paper.source_paper_id or paper.id,
                        "source_url": paper.source_url,
                        "pdf_url": paper.pdf_url,
                    }
                )
            )

        seen_keys: set[str] = set(attached_keys)
        normalized: list[dict[str, Any]] = []
        for raw_candidate in raw_candidates:
            title = self._clean_optional_string(raw_candidate.get("title"))
            if not title:
                continue

            candidate = dict(raw_candidate)
            candidate["title"] = title
            candidate["source"] = self._clean_optional_string(candidate.get("source")) or "unknown"
            candidate["authors"] = list(candidate.get("authors") or [])
            candidate["abstract"] = self._clean_optional_string(candidate.get("abstract"))
            candidate["source_url"] = self._clean_optional_string(candidate.get("source_url"))
            candidate["pdf_url"] = self._clean_optional_string(candidate.get("pdf_url"))
            candidate["source_paper_id"] = self._clean_optional_string(
                candidate.get("source_paper_id")
            )

            arxiv_id = self._resolve_candidate_arxiv_id(candidate)
            if arxiv_id:
                candidate["arxiv_id"] = arxiv_id
                candidate["source_paper_id"] = candidate.get("source_paper_id") or arxiv_id
                candidate["pdf_url"] = candidate.get("pdf_url") or f"https://arxiv.org/pdf/{arxiv_id}"
            else:
                candidate["arxiv_id"] = None

            if not candidate.get("source_url") and not candidate.get("source_paper_id"):
                continue

            identity_keys = self._source_identity_keys(candidate)
            if not identity_keys:
                continue
            if any(key in seen_keys for key in identity_keys):
                continue

            seen_keys.update(identity_keys)
            candidate["candidate_id"] = f"cand_{len(normalized) + 1}"
            candidate["pdf_available"] = bool(candidate.get("pdf_available") or candidate.get("pdf_url"))
            candidate["domain"] = self._url_domain(candidate.get("source_url"))
            normalized.append(candidate)

        return normalized

    def _ranked_candidates_from_provider_payload(
        self,
        *,
        payload: dict[str, Any],
        candidates: list[dict[str, Any]],
        local_ranked: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        ranked_items = payload.get("ranked_candidates")
        if not isinstance(ranked_items, list):
            candidate_alias_items = payload.get("candidates")
            if isinstance(candidate_alias_items, list):
                ranked_items = candidate_alias_items
            else:
                payload_shape = self._source_ranker_payload_shape(payload)
                logger.warning(
                    "Source ranker returned invalid provider payload; payload_shape=%s",
                    payload_shape,
                    extra={"payload_shape": payload_shape},
                )
                return local_ranked[:WRITER_SOURCE_LIMIT], [
                    "Source ranker returned invalid output; used local ranking."
                ]

        candidate_by_id = {
            str(candidate["candidate_id"]): candidate for candidate in candidates
        }
        ranked: list[dict[str, Any]] = []
        used_ids: set[str] = set()
        rejected_ids: set[str] = set()
        invalid_id_count = 0

        for item in ranked_items:
            if not isinstance(item, dict):
                continue
            candidate_id = item.get("candidate_id")
            if not isinstance(candidate_id, str) or candidate_id not in candidate_by_id:
                invalid_id_count += 1
                continue
            if item.get("keep") is False:
                rejected_ids.add(candidate_id)
                continue
            if item.get("keep") is not True or candidate_id in used_ids:
                continue
            ranked.append(candidate_by_id[candidate_id])
            used_ids.add(candidate_id)
            if len(ranked) >= WRITER_SOURCE_LIMIT:
                break

        for candidate in local_ranked:
            candidate_id = str(candidate["candidate_id"])
            if candidate_id in used_ids or candidate_id in rejected_ids:
                continue
            ranked.append(candidate)
            used_ids.add(candidate_id)
            if len(ranked) >= WRITER_SOURCE_LIMIT:
                break

        raw_warnings = payload.get("warnings", [])
        warnings = (
            [
                str(warning).strip()
                for warning in raw_warnings
                if str(warning).strip()
            ]
            if isinstance(raw_warnings, list)
            else []
        )
        if invalid_id_count:
            payload_shape = self._source_ranker_payload_shape(payload)
            logger.warning(
                "Source ranker returned unknown candidate IDs; invalid_id_count=%s; payload_shape=%s",
                invalid_id_count,
                payload_shape,
                extra={
                    "invalid_id_count": invalid_id_count,
                    "payload_shape": payload_shape,
                },
            )
            warnings.append("Source ranker returned unknown candidate IDs; filled with local ranking.")
        return ranked, warnings

    def _source_ranker_payload_shape(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Summarize provider payload structure without logging raw source content."""

        ranked_items = payload.get("ranked_candidates")
        warnings = payload.get("warnings")
        shape: dict[str, Any] = {
            "ranked_candidates_type": type(ranked_items).__name__,
            "top_level_keys": sorted(str(key) for key in payload.keys()),
            "warnings_type": type(warnings).__name__,
        }
        if "candidates" in payload:
            shape["candidates_type"] = type(payload.get("candidates")).__name__
        if isinstance(ranked_items, list):
            shape["ranked_candidates_count"] = len(ranked_items)
            shape["ranked_candidate_item_types"] = sorted(
                {type(item).__name__ for item in ranked_items}
            )
        return shape

    def _local_rank_source_candidates(
        self,
        *,
        doc: WriterDocument,
        section: WriterSection | None,
        candidates: list[dict[str, Any]],
        query: str,
    ) -> list[dict[str, Any]]:
        context_terms = self._rank_tokens(
            " ".join(
                part
                for part in [
                    query,
                    doc.topic,
                    doc.thesis or "",
                    section.title if section else "",
                    section.outline_text if section and section.outline_text else "",
                    " ".join((section.user_inputs_json or {}).values()) if section else "",
                ]
                if part
            )
        )
        scored: list[tuple[float, int, dict[str, Any]]] = []
        for index, candidate in enumerate(candidates):
            title_terms = self._rank_tokens(str(candidate.get("title") or ""))
            body_terms = self._rank_tokens(str(candidate.get("abstract") or ""))
            title_overlap = len(title_terms & context_terms)
            body_overlap = len(body_terms & context_terms)
            score = (title_overlap * 4.0) + body_overlap
            raw_tavily_score = candidate.get("tavily_score")
            if isinstance(raw_tavily_score, int | float):
                score += float(raw_tavily_score)
            if candidate.get("pdf_available"):
                score += 0.25
            if candidate.get("source") == "arxiv":
                score += 0.2
            scored.append((score, index, candidate))

        scored.sort(key=lambda item: (-item[0], item[1]))
        return [candidate for _, _, candidate in scored]

    def _source_ranker_prompt_payload(
        self,
        *,
        doc: WriterDocument,
        section: WriterSection | None,
        candidates: list[dict[str, Any]],
        query: str,
    ) -> dict[str, Any]:
        user_answers = dict(section.user_inputs_json or {}) if section else {}
        return {
            "query": query,
            "document": {
                "topic": doc.topic,
                "thesis": doc.thesis,
            },
            "section": {
                "title": section.title if section else None,
                "section_type": section.section_type if section else None,
                "outline_text": section.outline_text if section else None,
                "user_answers": user_answers,
                "notes": user_answers.get("__notes__"),
            },
            "candidates": [
                {
                    "candidate_id": candidate["candidate_id"],
                    "title": candidate.get("title"),
                    "source_type": candidate.get("source"),
                    "url": candidate.get("source_url"),
                    "domain": candidate.get("domain"),
                    "abstract_or_snippet": candidate.get("abstract"),
                    "pdf_available": bool(candidate.get("pdf_available")),
                    "arxiv_id": candidate.get("arxiv_id"),
                    "tavily_score": candidate.get("tavily_score"),
                }
                for candidate in candidates
            ],
        }

    def _candidate_from_tavily_result(
        self, result: Any, *, source: str
    ) -> dict[str, Any]:
        source_url = self._clean_optional_string(getattr(result, "url", None))
        arxiv_id = self._extract_arxiv_id(source_url or "") if source_url else None
        return {
            "title": getattr(result, "title", None),
            "authors": [],
            "year": None,
            "abstract": (getattr(result, "content", "") or "")[:500] or None,
            "source": source,
            "source_paper_id": arxiv_id,
            "source_url": source_url,
            "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else None,
            "pdf_available": bool(arxiv_id),
            "arxiv_id": arxiv_id,
            "tavily_score": getattr(result, "score", None),
        }

    def _build_section_source_query(self, *, doc: WriterDocument, section: WriterSection) -> str:
        user_inputs = dict(section.user_inputs_json or {})
        query_parts = [
            doc.topic,
            doc.thesis or "",
            section.title,
            section.outline_text or "",
            *[value for value in user_inputs.values() if value],
        ]
        return " ".join(part.strip() for part in query_parts if part and part.strip())[:500]

    def _public_source_candidate(self, candidate: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": candidate["title"],
            "authors": list(candidate.get("authors") or []),
            "year": candidate.get("year"),
            "abstract": candidate.get("abstract"),
            "source": candidate.get("source") or "unknown",
            "source_paper_id": candidate.get("source_paper_id"),
            "source_url": candidate.get("source_url"),
            "pdf_url": candidate.get("pdf_url"),
            "pdf_available": bool(candidate.get("pdf_available")),
            "arxiv_id": candidate.get("arxiv_id"),
        }

    def _source_identity_keys(self, candidate: dict[str, Any]) -> set[str]:
        keys: set[str] = set()
        arxiv_id = self._resolve_candidate_arxiv_id(candidate)
        if arxiv_id:
            keys.add(f"arxiv:{self._normalize_arxiv_id(arxiv_id)}")

        source_paper_id = self._clean_optional_string(candidate.get("source_paper_id"))
        if source_paper_id:
            keys.add(f"source:{self._normalize_source_id(source_paper_id)}")

        source_url = self._normalize_source_url(candidate.get("source_url"))
        if source_url:
            keys.add(f"url:{source_url}")
        return keys

    def _resolve_candidate_arxiv_id(self, candidate: dict[str, Any]) -> str | None:
        raw_arxiv_id = self._clean_optional_string(candidate.get("arxiv_id"))
        if raw_arxiv_id and ARXIV_ID_VALUE_RE.match(raw_arxiv_id):
            return raw_arxiv_id

        for key in ("source_url", "pdf_url"):
            value = self._clean_optional_string(candidate.get(key))
            if value:
                arxiv_id = self._extract_arxiv_id(value)
                if arxiv_id:
                    return arxiv_id

        source_paper_id = self._clean_optional_string(candidate.get("source_paper_id"))
        if source_paper_id and ARXIV_ID_VALUE_RE.match(source_paper_id):
            return source_paper_id
        return None

    def _normalize_arxiv_id(self, arxiv_id: str) -> str:
        return re.sub(r"v\d+$", "", arxiv_id.strip().lower())

    def _normalize_source_id(self, source_id: str) -> str:
        normalized = source_id.strip().lower()
        if ARXIV_ID_VALUE_RE.match(normalized):
            return self._normalize_arxiv_id(normalized)
        return normalized

    def _normalize_source_url(self, url: object) -> str | None:
        value = self._clean_optional_string(url)
        if not value:
            return None
        parsed = urlparse(value)
        if not parsed.netloc:
            return value.rstrip("/").lower()
        path = parsed.path.rstrip("/")
        return urlunparse(
            (parsed.scheme.lower(), parsed.netloc.lower(), path, "", "", "")
        ).rstrip("/")

    def _url_domain(self, url: object) -> str | None:
        value = self._clean_optional_string(url)
        if not value:
            return None
        domain = urlparse(value).netloc.lower()
        return domain or None

    def _rank_tokens(self, text: str) -> set[str]:
        return {
            token.lower()
            for token in SOURCE_RANK_TOKEN_RE.findall(text)
            if len(token) >= 3
        }

    def _clean_optional_string(self, value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    async def attach_paper_id(
        self,
        *,
        session: AsyncSession,
        document_id: str,
        user_id: str,
        paper_id: str,
    ) -> str:
        """Attach an already-existing Paper record (e.g. from PDF upload) to a writer document."""
        doc = await self.get_document(session=session, document_id=document_id, user_id=user_id)
        paper = await session.get(Paper, paper_id)
        if paper is None:
            raise WriterDocumentNotFoundError(f"Paper '{paper_id}' not found.")
        if not await self._can_use_paper(session=session, doc=doc, user_id=user_id, paper=paper):
            raise WriterDocumentPermissionError("Paper does not belong to this writer document.")
        await self._attach_paper_to_document(
            session=session,
            doc=doc,
            paper=paper,
            source_origin="manual",
        )
        return paper_id

    async def import_project_sources(
        self,
        *,
        session: AsyncSession,
        document_id: str,
        user_id: str,
        project_id: str,
        paper_ids: list[str],
    ) -> list[str]:
        """Import owned project papers as document-owned source copies."""

        doc = await self.get_document(session=session, document_id=document_id, user_id=user_id)
        project = await session.get(Project, project_id)
        if project is None:
            raise WriterDocumentNotFoundError(f"Project '{project_id}' not found.")
        if project.user_id != user_id:
            raise WriterDocumentPermissionError("Access denied.")

        unique_paper_ids = self._ordered_unique(paper_ids)
        result = await session.execute(
            select(Paper)
            .options(
                selectinload(Paper.summary),
                selectinload(Paper.chunks),
            )
            .where(Paper.project_id == project_id, Paper.id.in_(unique_paper_ids))
        )
        papers_by_id = {paper.id: paper for paper in result.scalars().all()}
        missing_ids = [paper_id for paper_id in unique_paper_ids if paper_id not in papers_by_id]
        if missing_ids:
            raise WriterDocumentNotFoundError("One or more project papers were not found.")

        imported_ids: list[str] = []
        for source_paper_id in unique_paper_ids:
            imported = await self._copy_project_paper_for_document(
                session=session,
                source_paper=papers_by_id[source_paper_id],
                user_id=user_id,
            )
            await self._attach_paper_to_document(
                session=session,
                doc=doc,
                paper=imported,
                source_origin="project_import",
                notes=f"Imported from project {project_id} paper {source_paper_id}",
                commit=False,
            )
            imported_ids.append(imported.id)

        await session.commit()
        return imported_ids

    async def upload_source_pdf(
        self,
        *,
        session: AsyncSession,
        document_id: str,
        user_id: str,
        filename: str,
        content_type: str | None,
        content: bytes,
    ) -> ReferenceFile:
        """Upload a PDF directly into a writer document source library."""

        doc = await self.get_document(session=session, document_id=document_id, user_id=user_id)
        ref_file = await self.reference_file_service.create_reference_file(
            session=session,
            project=None,
            user_id=doc.user_id,
            filename=filename,
            content_type=content_type,
            content=content,
        )
        if ref_file.paper is not None:
            await self._attach_paper_to_document(
                session=session,
                doc=doc,
                paper=ref_file.paper,
                source_origin="upload",
            )
        return ref_file

    async def _fetch_arxiv_candidates(
        self, query: str, *, limit: int = WRITER_ARXIV_SOURCE_POOL
    ) -> list[dict[str, Any]]:
        from backend.services.arxiv import search_papers as arxiv_search

        papers = await arxiv_search(query=query, year_start=2018, limit=limit)
        return [dict(p) for p in papers]

    def _extract_arxiv_id(self, url: str) -> str | None:
        m = ARXIV_ID_RE.search(url)
        return m.group(1) if m else None

    def _default_outline_text(
        self,
        *,
        paper_type: str = "imrad",
        section_type: str,
        topic: str,
        thesis: str | None,
    ) -> str:
        normalized_paper_type = paper_type.strip().lower()
        if normalized_paper_type == "research" and section_type in RESEARCH_SECTION_OUTLINES:
            outline = RESEARCH_SECTION_OUTLINES[section_type]
            if section_type not in {"methods", "results"}:
                focus = f" Topic: {topic}."
                if thesis:
                    focus += f" Thesis: {thesis}."
                return f"{outline}{focus}"
            return outline
        if normalized_paper_type == "survey" and section_type in SURVEY_SECTION_OUTLINES:
            outline = SURVEY_SECTION_OUTLINES[section_type]
            if section_type not in {"methods", "results"}:
                focus = f" Topic: {topic}."
                if thesis:
                    focus += f" Thesis: {thesis}."
                return f"{outline}{focus}"
            return outline

        base = f"Discuss '{topic}'"
        if thesis:
            base += f" with focus on: {thesis}"
        templates: dict[str, str] = {
            "abstract": f"Summarize the full paper on {topic}.",
            "intro": f"Motivate the problem, state the research gap, and introduce the contribution. Topic: {topic}.",
            "related_work": f"Survey prior work most relevant to {topic}.",
            "methods": f"Describe the methodology used in the {topic} study.",
            "results": f"Present quantitative and qualitative results for {topic}.",
            "discussion": f"Interpret findings, limitations, and implications for {topic}.",
            "conclusion": f"Summarize contributions and future directions for {topic}.",
        }
        return templates.get(section_type, base)

    def _requires_structured_methods_outline(
        self,
        *,
        doc: WriterDocument,
        section: WriterSection,
    ) -> bool:
        paper_type = doc.paper_type.strip().lower()
        if paper_type not in {"research", "survey"} or section.section_type != "methods":
            return False
        return r"\subsection{" not in (section.outline_text or "")

    def _requires_structured_results_outline(
        self,
        *,
        doc: WriterDocument,
        section: WriterSection,
    ) -> bool:
        paper_type = doc.paper_type.strip().lower()
        if paper_type not in {"research", "survey"} or section.section_type != "results":
            return False
        return r"\subsection{" not in (section.outline_text or "")

    def _substitute_citation_keys(
        self, text: str, citation_keys: dict[str, str]
    ) -> str:
        def replace_citation(match: re.Match[str]) -> str:
            command = match.group(1)
            paper_ids = [paper_id.strip() for paper_id in match.group(2).split(",")]
            keys = [citation_keys.get(paper_id, paper_id) for paper_id in paper_ids if paper_id]
            return f"{command}{{{','.join(keys)}}}"

        return CITE_COMMAND_PATTERN.sub(replace_citation, text)

    def _extract_cited_paper_ids_from_sections(self, sections: list[WriterSection]) -> list[str]:
        ids: list[str] = []
        for section in sections:
            if not section.draft_latex:
                continue
            for match in CITE_COMMAND_PATTERN.finditer(section.draft_latex):
                ids.extend(
                    paper_id.strip()
                    for paper_id in match.group(2).split(",")
                    if paper_id.strip()
                )
        return self._ordered_unique(ids)

    def _ordered_unique(self, values: list[str]) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            ordered.append(value)
        return ordered
