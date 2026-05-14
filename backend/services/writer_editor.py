"""Service glue for writer editor previews and patch application."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.agents.writer_editor import (
    EditPatch,
    NewResult,
    TextSpan,
    WebSearchHit,
    WriterEditorAgent,
)
from backend.db.models import WriterDocument, WriterDocumentSource, WriterSection
from backend.services.tavily import ACADEMIC_DOMAINS, TavilySearchService
from backend.services.writer_documents import (
    WriterDocumentNotFoundError,
    WriterDocumentPermissionError,
    WriterDocumentService,
    WriterSectionNotFoundError,
)


class WriterEditConflictError(RuntimeError):
    """Raised when a preview patch no longer matches the current section draft."""


class WriterEditorService:
    def __init__(
        self,
        *,
        agent: WriterEditorAgent | None = None,
        tavily_service: TavilySearchService | None = None,
        writer_document_service: WriterDocumentService | None = None,
    ) -> None:
        self.agent = agent or WriterEditorAgent()
        self.tavily_service = tavily_service or TavilySearchService()
        self.writer_document_service = writer_document_service or WriterDocumentService()

    async def preview(
        self,
        *,
        session: AsyncSession,
        document_id: str,
        section_id: str,
        user_id: str,
        instruction: str,
        span: TextSpan | None,
        insertion_offset: int | None,
        new_results: list[NewResult],
        web_search: bool = False,
        web_query: str | None = None,
    ) -> EditPatch:
        section, doc = await self._load_section(
            session=session,
            document_id=document_id,
            section_id=section_id,
            user_id=user_id,
        )
        draft = section.draft_latex or ""
        web_hits = await self._web_hits(
            query=web_query or instruction or section.title,
            enabled=web_search,
        )
        return await self.agent.edit(
            draft=draft,
            instruction=instruction,
            section_heading=section.title,
            span=span,
            insertion_offset=insertion_offset,
            new_results=new_results,
            web_hits=web_hits,
            known_citation_keys=self._known_citation_keys(doc),
        )

    async def apply(
        self,
        *,
        session: AsyncSession,
        document_id: str,
        section_id: str,
        user_id: str,
        patch: EditPatch,
    ) -> WriterSection:
        section, _ = await self._load_section(
            session=session,
            document_id=document_id,
            section_id=section_id,
            user_id=user_id,
        )
        draft = section.draft_latex or ""
        if patch.span.start < 0 or patch.span.end < patch.span.start or patch.span.end > len(draft):
            raise WriterEditConflictError("Editor patch is out of bounds for the current draft.")
        if draft[patch.span.start : patch.span.end] != patch.original_text:
            raise WriterEditConflictError("Editor patch is stale; preview the edit again.")

        new_draft = draft[: patch.span.start] + patch.new_text + draft[patch.span.end :]
        return await self.writer_document_service.save_section_edit(
            session=session,
            section_id=section_id,
            user_id=user_id,
            draft_latex=new_draft,
        )

    async def _load_section(
        self,
        *,
        session: AsyncSession,
        document_id: str,
        section_id: str,
        user_id: str,
    ) -> tuple[WriterSection, WriterDocument]:
        result = await session.execute(
            select(WriterSection)
            .options(
                selectinload(WriterSection.document)
                .selectinload(WriterDocument.sources)
                .selectinload(WriterDocumentSource.paper),
            )
            .where(WriterSection.id == section_id)
        )
        section = result.scalar_one_or_none()
        if section is None or section.writer_document_id != document_id:
            raise WriterSectionNotFoundError(f"Section '{section_id}' not found.")
        doc = section.document
        if doc is None:
            raise WriterDocumentNotFoundError(f"Document '{document_id}' not found.")
        if doc.user_id != user_id:
            raise WriterDocumentPermissionError("Access denied.")
        return section, doc

    async def _web_hits(self, *, query: str, enabled: bool) -> list[WebSearchHit]:
        if not enabled:
            return []
        response = await self.tavily_service.search(
            query,
            max_results=5,
            include_domains=ACADEMIC_DOMAINS,
        )
        hits: list[WebSearchHit] = []
        for result in response.results[:5]:
            if not result.url:
                continue
            hits.append(
                WebSearchHit(
                    title=result.title,
                    url=result.url,
                    snippet=result.content,
                )
            )
        return hits

    def _known_citation_keys(self, doc: WriterDocument) -> set[str]:
        keys = set(doc.source_paper_ids_json or [])
        for source in doc.sources:
            if source.paper_id:
                keys.add(source.paper_id)
        return keys
