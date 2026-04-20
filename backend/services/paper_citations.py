from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Paper
from backend.services.semantic_scholar import (
    SemanticScholarPaperDetails,
    SemanticScholarPaperLookupError,
    SemanticScholarPaperNotFoundError,
    SemanticScholarProviderError,
    get_paper_citations,
    get_paper_details,
    get_paper_references,
)


class CitationLookupError(RuntimeError):
    """Base error for project paper citation lookups."""


class CitationResolutionError(CitationLookupError):
    """Raised when a project paper cannot be resolved exactly upstream."""


class CitationNotFoundError(CitationLookupError):
    """Raised when the upstream provider cannot find the exact paper."""


class CitationProviderError(CitationLookupError):
    """Raised when the upstream provider fails unexpectedly."""


@dataclass(frozen=True)
class CitationGraphResult:
    """Resolved citation graph payload for a project paper."""

    paper_id: str
    resolved_by: str
    resolved_source_paper_id: str
    citation_count: int | None
    reference_count: int | None
    cited_by: list[dict[str, object]]
    references: list[dict[str, object]]


class SemanticScholarCitationClient(Protocol):
    """Minimal provider interface for exact paper citation lookups."""

    async def get_paper_details(self, paper_identifier: str) -> SemanticScholarPaperDetails:
        """Resolve one upstream paper exactly."""

    async def get_paper_citations(
        self,
        paper_identifier: str,
        *,
        limit: int,
    ) -> list[dict[str, object]]:
        """Return papers citing the resolved paper."""

    async def get_paper_references(
        self,
        paper_identifier: str,
        *,
        limit: int,
    ) -> list[dict[str, object]]:
        """Return papers referenced by the resolved paper."""


class DefaultSemanticScholarCitationClient:
    """Thin adapter over the Semantic Scholar helper functions."""

    async def get_paper_details(self, paper_identifier: str) -> SemanticScholarPaperDetails:
        return await get_paper_details(paper_identifier)

    async def get_paper_citations(
        self,
        paper_identifier: str,
        *,
        limit: int,
    ) -> list[dict[str, object]]:
        return await get_paper_citations(paper_identifier, limit=limit)

    async def get_paper_references(
        self,
        paper_identifier: str,
        *,
        limit: int,
    ) -> list[dict[str, object]]:
        return await get_paper_references(paper_identifier, limit=limit)


class PaperCitationService:
    """Resolve a project paper to Semantic Scholar and return its citation graph."""

    def __init__(
        self,
        *,
        semantic_scholar_client: SemanticScholarCitationClient | None = None,
    ) -> None:
        self.semantic_scholar_client = (
            semantic_scholar_client or DefaultSemanticScholarCitationClient()
        )

    async def get_citation_graph(
        self,
        *,
        session: AsyncSession,
        paper: Paper,
        limit: int,
    ) -> CitationGraphResult:
        del session

        resolved_by, paper_details = await self._resolve_semantic_scholar_paper(paper)

        try:
            cited_by, references = await self._fetch_graph_lists(
                resolved_source_paper_id=paper_details.paper_id,
                limit=limit,
            )
        except SemanticScholarProviderError as error:
            raise CitationProviderError(str(error)) from error

        return CitationGraphResult(
            paper_id=paper.id,
            resolved_by=resolved_by,
            resolved_source_paper_id=paper_details.paper_id,
            citation_count=paper_details.citation_count,
            reference_count=paper_details.reference_count,
            cited_by=cited_by,
            references=references,
        )

    async def _resolve_semantic_scholar_paper(
        self,
        paper: Paper,
    ) -> tuple[str, SemanticScholarPaperDetails]:
        candidate_identifiers = self._build_resolution_candidates(paper)
        if not candidate_identifiers:
            raise CitationResolutionError(
                "Paper cannot be resolved exactly to Semantic Scholar. "
                "A Semantic Scholar id, arXiv id, or DOI is required."
            )

        not_found_count = 0
        for resolved_by, paper_identifier in candidate_identifiers:
            try:
                paper_details = await self.semantic_scholar_client.get_paper_details(
                    paper_identifier
                )
            except SemanticScholarPaperLookupError as error:
                raise CitationResolutionError(str(error)) from error
            except SemanticScholarPaperNotFoundError:
                not_found_count += 1
                continue
            except SemanticScholarProviderError as error:
                raise CitationProviderError(str(error)) from error

            return resolved_by, paper_details

        if not_found_count:
            raise CitationNotFoundError("Exact paper was not found in Semantic Scholar.")

        raise CitationResolutionError(
            "Paper cannot be resolved exactly to Semantic Scholar."
        )

    def _build_resolution_candidates(self, paper: Paper) -> list[tuple[str, str]]:
        candidates: list[tuple[str, str]] = []
        seen_identifiers: set[str] = set()

        def add_candidate(resolved_by: str, raw_identifier: str | None) -> None:
            if raw_identifier is None:
                return
            normalized_identifier = raw_identifier.strip()
            if not normalized_identifier or normalized_identifier in seen_identifiers:
                return
            seen_identifiers.add(normalized_identifier)
            candidates.append((resolved_by, normalized_identifier))

        if paper.source == "semantic_scholar":
            add_candidate("semantic_scholar_paper_id", paper.source_paper_id)

        if paper.source == "arxiv":
            add_candidate(
                "arxiv_id",
                f"ARXIV:{paper.source_paper_id}" if paper.source_paper_id else None,
            )
            add_candidate("arxiv_url", f"URL:{paper.source_url}" if paper.source_url else None)

        add_candidate("doi", f"DOI:{paper.doi}" if paper.doi else None)

        return candidates

    async def _fetch_graph_lists(
        self,
        *,
        resolved_source_paper_id: str,
        limit: int,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        cited_by = await self.semantic_scholar_client.get_paper_citations(
            resolved_source_paper_id,
            limit=limit,
        )
        references = await self.semantic_scholar_client.get_paper_references(
            resolved_source_paper_id,
            limit=limit,
        )
        return cited_by, references
