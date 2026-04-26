from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.agents.qa import WriterQAAgent, WriterQaFlag
from backend.agents.writer import (
    GroundedWriterAgent,
    WriterBodyBlock,
    WriterGenerationResult,
    WriterPaperContext,
)
from backend.config import get_settings
from backend.db.models import Paper, PaperChunk, Project, WriterOutput
from backend.services.citations import CitationArtifactBundle, CitationFormatter
from backend.services.document_extraction import (
    DocumentExtractionError,
    PaperDocumentExtractionService,
    embed_texts_with_feature,
)
from backend.services.embeddings import EmbeddingService
from backend.services.research_utils import cosine_similarity

DEFAULT_OUTPUT_TARGET = "markdown"
DEFAULT_REFERENCE_STYLE = "ieee"
LATEX_OUTPUT_TARGET = "latex"
LATEX_CITATION_MODE = "latex_cite"
MAX_EVIDENCE_SNIPPETS_PER_PAPER = 2
MAX_EVIDENCE_SNIPPET_CHARS = 420
RECOGNIZED_REFERENCE_STYLES = {"ieee", "apa", "chicago", "bibtex"}


class DocumentExtractionClient(Protocol):
    """Minimal document extraction interface used by writer output generation."""

    async def ensure_document_chunks(
        self,
        *,
        session: AsyncSession,
        paper: Paper,
    ) -> object:
        """Ensure chunk grounding exists for a paper."""


class EmbeddingClient(Protocol):
    """Minimal embedding interface used by writer output generation."""

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings for the provided texts."""


@dataclass(frozen=True)
class WriterRenderResult:
    """Rendered writer output plus the artifact ids it depends on."""

    body: str
    references: list[str]
    bibtex_entries: list[str]
    thebibliography: str | None
    citations_used: list[str]
    artifact_paper_ids: list[str]
    citation_bundle: CitationArtifactBundle


class WriterOutputService:
    """Generate, QA, and persist user-invoked writer outputs."""

    def __init__(
        self,
        *,
        writer_agent: GroundedWriterAgent | None = None,
        qa_agent: WriterQAAgent | None = None,
        extraction_service: DocumentExtractionClient | None = None,
        embedding_service: EmbeddingClient | None = None,
        citation_formatter: CitationFormatter | None = None,
    ) -> None:
        settings = get_settings()
        self.writer_agent = writer_agent or GroundedWriterAgent()
        self.qa_agent = qa_agent or WriterQAAgent()
        self.extraction_service = extraction_service or PaperDocumentExtractionService()
        self.embedding_service = embedding_service or EmbeddingService()
        self.citation_formatter = citation_formatter or CitationFormatter()
        self.retrieval_top_k = settings.paper_retrieval_top_k

    async def generate_output(
        self,
        *,
        session: AsyncSession,
        project: Project,
        paper_ids: list[str],
        instruction: str,
        output_target: str | None,
        citation_mode: str | None,
        reference_style: str | None,
        include_references: bool,
        max_words: int | None,
    ) -> WriterOutput:
        selected_papers = await self._load_selected_papers(
            session=session,
            project_id=project.id,
            requested_paper_ids=paper_ids,
        )
        resolved_output_target = output_target or DEFAULT_OUTPUT_TARGET
        resolved_citation_mode = self._resolve_citation_mode(
            project=project,
            output_target=resolved_output_target,
            citation_mode=citation_mode,
        )
        resolved_reference_style = self._resolve_reference_style(
            project=project,
            citation_mode=resolved_citation_mode,
            reference_style=reference_style,
        )
        paper_contexts, context_warnings = await self._build_paper_contexts(
            session=session,
            selected_papers=selected_papers,
            instruction=instruction,
        )
        writer_result = await self.writer_agent.generate(
            paper_contexts=paper_contexts,
            instruction=instruction,
            output_target=resolved_output_target,
            citation_mode=resolved_citation_mode,
            reference_style=resolved_reference_style,
            include_references=include_references,
            max_words=max_words,
        )
        render_result = self._render_output(
            selected_papers=selected_papers,
            writer_result=writer_result,
            instruction=instruction,
            output_target=resolved_output_target,
            citation_mode=resolved_citation_mode,
            reference_style=resolved_reference_style,
        )
        warnings = self._dedupe_strings([*context_warnings, *writer_result.warnings])
        qa_flags = self.qa_agent.validate_output(
            body=render_result.body,
            references=render_result.references,
            bibtex_entries=render_result.bibtex_entries,
            thebibliography=render_result.thebibliography,
            selected_papers=selected_papers,
            citation_mode=resolved_citation_mode,
            artifact_paper_ids=render_result.artifact_paper_ids,
            citation_keys_by_paper_id=render_result.citation_bundle.citation_keys_by_paper_id,
        )

        writer_output = WriterOutput(
            project_id=project.id,
            selected_paper_ids_json=[paper.id for paper in selected_papers],
            paper_snapshot_json=[self._serialize_paper_snapshot(paper) for paper in selected_papers],
            instruction=instruction.strip(),
            output_target=resolved_output_target,
            citation_mode=resolved_citation_mode,
            reference_style=resolved_reference_style,
            include_references=include_references,
            max_words=max_words,
            body=render_result.body,
            references_json=render_result.references,
            bibtex_entries_json=render_result.bibtex_entries,
            thebibliography_text=render_result.thebibliography,
            citations_used_json=render_result.citations_used,
            warnings_json=warnings,
            qa_flags_json=[self._serialize_qa_flag(flag) for flag in qa_flags],
        )
        session.add(writer_output)
        await session.commit()
        await session.refresh(writer_output)
        return writer_output

    async def _load_selected_papers(
        self,
        *,
        session: AsyncSession,
        project_id: str,
        requested_paper_ids: list[str],
    ) -> list[Paper]:
        unique_paper_ids = list(dict.fromkeys(requested_paper_ids))
        result = await session.execute(
            select(Paper)
            .options(selectinload(Paper.summary))
            .where(
                Paper.project_id == project_id,
                Paper.id.in_(unique_paper_ids),
            )
        )
        papers_by_id = {paper.id: paper for paper in result.scalars().all()}
        missing_paper_ids = [paper_id for paper_id in unique_paper_ids if paper_id not in papers_by_id]
        if missing_paper_ids:
            raise LookupError("One or more selected papers were not found in the project.")

        return [papers_by_id[paper_id] for paper_id in unique_paper_ids]

    async def _build_paper_contexts(
        self,
        *,
        session: AsyncSession,
        selected_papers: list[Paper],
        instruction: str,
    ) -> tuple[list[WriterPaperContext], list[str]]:
        instruction_embedding = await self._embed_instruction(instruction)
        paper_contexts: list[WriterPaperContext] = []
        warnings: list[str] = []

        for paper in selected_papers:
            chunks, chunk_warnings = await self._load_relevant_chunks(
                session=session,
                paper=paper,
                instruction_embedding=instruction_embedding[0] if instruction_embedding else [],
            )
            metadata_warnings = self._build_metadata_warnings(paper)
            warnings.extend(chunk_warnings)
            warnings.extend(metadata_warnings)
            summary = paper.summary
            paper_contexts.append(
                WriterPaperContext(
                    paper_id=paper.id,
                    title=paper.title,
                    authors=list(paper.authors),
                    year=paper.year,
                    abstract=paper.abstract,
                    problem=summary.problem if summary is not None else None,
                    method=summary.method if summary is not None else None,
                    result=summary.result if summary is not None else None,
                    relevance_to_topic=summary.relevance_to_topic if summary is not None else None,
                    evidence_snippets=chunks,
                    metadata_warnings=metadata_warnings,
                )
            )

        return paper_contexts, self._dedupe_strings(warnings)

    async def _embed_instruction(self, instruction: str) -> list[list[float]]:
        try:
            return await embed_texts_with_feature(
                self.embedding_service,
                [instruction.strip()],
                feature="writer_retrieval_embedding",
            )
        except Exception as error:
            if isinstance(self.embedding_service, EmbeddingService):
                return self.embedding_service.embed_texts_locally([instruction.strip()])
            raise RuntimeError("Writer instruction embedding failed.") from error

    async def _load_relevant_chunks(
        self,
        *,
        session: AsyncSession,
        paper: Paper,
        instruction_embedding: list[float],
    ) -> tuple[list[str], list[str]]:
        warnings: list[str] = []
        chunk_rows = await self._fetch_paper_chunks(session=session, paper_id=paper.id)

        if not chunk_rows and paper.pdf_url:
            try:
                await self.extraction_service.ensure_document_chunks(session=session, paper=paper)
            except DocumentExtractionError as error:
                warnings.append(f"Paper '{paper.title}' could not be grounded from its PDF: {error}")
            chunk_rows = await self._fetch_paper_chunks(session=session, paper_id=paper.id)

        if not chunk_rows or not instruction_embedding:
            return [], warnings

        ranked_chunks: list[tuple[float, PaperChunk]] = []
        for chunk in chunk_rows:
            chunk_embedding = [float(value) for value in chunk.embedding_json]
            if not chunk_embedding:
                continue
            try:
                similarity = cosine_similarity(instruction_embedding, chunk_embedding)
            except ValueError:
                continue
            ranked_chunks.append((similarity, chunk))

        ranked_chunks.sort(key=lambda item: item[0], reverse=True)
        return [
            self._truncate_snippet(chunk.content)
            for _score, chunk in ranked_chunks[:MAX_EVIDENCE_SNIPPETS_PER_PAPER]
        ], warnings

    async def _fetch_paper_chunks(
        self,
        *,
        session: AsyncSession,
        paper_id: str,
    ) -> list[PaperChunk]:
        result = await session.execute(
            select(PaperChunk)
            .where(PaperChunk.paper_id == paper_id)
            .order_by(PaperChunk.chunk_index.asc())
        )
        return list(result.scalars().all())

    def _render_output(
        self,
        *,
        selected_papers: list[Paper],
        writer_result: WriterGenerationResult,
        instruction: str,
        output_target: str,
        citation_mode: str,
        reference_style: str,
    ) -> WriterRenderResult:
        citation_bundle = self.citation_formatter.prepare_bundle(
            papers=selected_papers,
            reference_style=reference_style,
        )
        sanitized_body_blocks = self._sanitize_body_blocks(
            writer_result.body_blocks,
            allowed_paper_ids={paper.id for paper in selected_papers},
        )
        citations_used = self._collect_citations_used(
            body_blocks=sanitized_body_blocks,
            selected_papers=selected_papers,
        )
        artifact_paper_ids = citations_used or [paper.id for paper in selected_papers]
        body = self._render_body(
            body_blocks=sanitized_body_blocks,
            instruction=instruction,
            output_target=output_target,
            citation_mode=citation_mode,
            citation_bundle=citation_bundle,
        )

        references: list[str] = []
        bibtex_entries: list[str] = []
        thebibliography: str | None = None

        if citation_mode == "bibtex_only":
            body = ""
            bibtex_entries = self.citation_formatter.format_bibtex_entries(
                paper_ids=artifact_paper_ids,
                bundle=citation_bundle,
            )
        elif citation_mode == "latex_cite":
            bibtex_entries = self.citation_formatter.format_bibtex_entries(
                paper_ids=artifact_paper_ids,
                bundle=citation_bundle,
            )
        elif citation_mode == "thebibliography":
            thebibliography = self.citation_formatter.format_thebibliography(
                paper_ids=artifact_paper_ids,
                bundle=citation_bundle,
            )
        else:
            references = self.citation_formatter.format_references(
                paper_ids=artifact_paper_ids,
                bundle=citation_bundle,
            )
            if reference_style == "bibtex":
                bibtex_entries = self.citation_formatter.format_bibtex_entries(
                    paper_ids=artifact_paper_ids,
                    bundle=citation_bundle,
                )

        return WriterRenderResult(
            body=body,
            references=references,
            bibtex_entries=bibtex_entries,
            thebibliography=thebibliography,
            citations_used=artifact_paper_ids if not body and artifact_paper_ids else citations_used,
            artifact_paper_ids=artifact_paper_ids,
            citation_bundle=citation_bundle,
        )

    def _render_body(
        self,
        *,
        body_blocks: list[WriterBodyBlock],
        instruction: str,
        output_target: str,
        citation_mode: str,
        citation_bundle: CitationArtifactBundle,
    ) -> str:
        if citation_mode == "bibtex_only":
            return ""

        paragraphs: list[str] = []
        heading = self._build_heading(instruction=instruction, output_target=output_target)
        if heading:
            paragraphs.append(heading)

        for block in body_blocks:
            normalized_text = block.text.strip()
            if not normalized_text:
                continue
            rendered_text = (
                self.citation_formatter.escape_latex_text(normalized_text)
                if output_target == LATEX_OUTPUT_TARGET
                else normalized_text
            )
            citation_marker = self.citation_formatter.format_inline_citation(
                paper_ids=block.paper_ids,
                citation_mode=citation_mode,
                bundle=citation_bundle,
            )
            paragraphs.append(
                f"{rendered_text} {citation_marker}".strip()
                if citation_marker
                else rendered_text
            )

        return "\n\n".join(paragraph for paragraph in paragraphs if paragraph).strip()

    def _build_heading(self, *, instruction: str, output_target: str) -> str | None:
        normalized_instruction = instruction.lower()
        if "bibtex" in normalized_instruction or "reference" in normalized_instruction:
            return None

        title: str | None = None
        if "related work" in normalized_instruction:
            title = "Related Work"
        elif "background" in normalized_instruction:
            title = "Background"
        elif "comparison" in normalized_instruction or "compare" in normalized_instruction:
            title = "Comparison"

        if title is None:
            return None
        if output_target == LATEX_OUTPUT_TARGET:
            command = "subsection" if "subsection" in normalized_instruction else "section"
            return rf"\{command}{{{self.citation_formatter.escape_latex_text(title)}}}"
        if output_target == "plain_text":
            return title
        return f"## {title}"

    def _sanitize_body_blocks(
        self,
        body_blocks: list[WriterBodyBlock],
        *,
        allowed_paper_ids: set[str],
    ) -> list[WriterBodyBlock]:
        sanitized_blocks: list[WriterBodyBlock] = []
        for block in body_blocks:
            supporting_paper_ids = [
                paper_id for paper_id in block.paper_ids if paper_id in allowed_paper_ids
            ]
            if not block.text.strip() or not supporting_paper_ids:
                continue
            sanitized_blocks.append(
                WriterBodyBlock(
                    text=block.text.strip(),
                    paper_ids=list(dict.fromkeys(supporting_paper_ids)),
                )
            )
        return sanitized_blocks

    def _collect_citations_used(
        self,
        *,
        body_blocks: list[WriterBodyBlock],
        selected_papers: list[Paper],
    ) -> list[str]:
        ordered_selected_paper_ids = [paper.id for paper in selected_papers]
        used_paper_id_set = {
            paper_id
            for block in body_blocks
            for paper_id in block.paper_ids
        }
        return [
            paper_id for paper_id in ordered_selected_paper_ids if paper_id in used_paper_id_set
        ]

    def _build_metadata_warnings(self, paper: Paper) -> list[str]:
        warnings: list[str] = []
        if not paper.authors:
            warnings.append(f"Paper '{paper.title}' is missing author metadata.")
        if paper.year is None:
            warnings.append(f"Paper '{paper.title}' is missing year metadata.")
        if paper.summary is None and not (paper.abstract or "").strip():
            warnings.append(f"Paper '{paper.title}' has no abstract or structured summary.")
        return warnings

    def _resolve_citation_mode(
        self,
        *,
        project: Project,
        output_target: str,
        citation_mode: str | None,
    ) -> str:
        if citation_mode is not None:
            return citation_mode
        if output_target == LATEX_OUTPUT_TARGET:
            return LATEX_CITATION_MODE

        project_citation_format = project.citation_format.strip().lower()
        if project_citation_format in {"apa", "chicago"}:
            return "author_year"
        return "numbered"

    def _resolve_reference_style(
        self,
        *,
        project: Project,
        citation_mode: str,
        reference_style: str | None,
    ) -> str:
        if reference_style is not None:
            return reference_style
        if citation_mode == "bibtex_only":
            return "bibtex"

        project_citation_format = project.citation_format.strip().lower()
        if project_citation_format in RECOGNIZED_REFERENCE_STYLES:
            return project_citation_format
        return DEFAULT_REFERENCE_STYLE

    def _truncate_snippet(self, text: str) -> str:
        normalized_text = " ".join(text.split())
        if len(normalized_text) <= MAX_EVIDENCE_SNIPPET_CHARS:
            return normalized_text
        return normalized_text[: MAX_EVIDENCE_SNIPPET_CHARS - 3].rstrip() + "..."

    def _serialize_paper_snapshot(self, paper: Paper) -> dict[str, object]:
        return {
            "id": paper.id,
            "title": paper.title,
            "authors": list(paper.authors),
            "year": paper.year,
            "doi": paper.doi,
            "source": paper.source,
            "source_url": paper.source_url,
            "pdf_url": paper.pdf_url,
        }

    def _serialize_qa_flag(self, flag: WriterQaFlag) -> dict[str, str]:
        return {
            "issue": flag.issue,
            "severity": flag.severity,
            "location": flag.location,
        }

    def _dedupe_strings(self, values: list[str]) -> list[str]:
        deduped_values: list[str] = []
        seen_values: set[str] = set()
        for value in values:
            normalized_value = value.strip()
            if not normalized_value or normalized_value in seen_values:
                continue
            seen_values.add(normalized_value)
            deduped_values.append(normalized_value)
        return deduped_values
