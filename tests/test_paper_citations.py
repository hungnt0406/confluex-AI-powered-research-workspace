from __future__ import annotations

import importlib
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.db.models import Paper


def require_module(module_path: str) -> Any:
    try:
        return importlib.import_module(module_path)
    except ModuleNotFoundError:
        pytest.fail(f"Missing module required by citation-graph tests: {module_path}")


def require_attr(target: object, attr_name: str) -> Any:
    attr = getattr(target, attr_name, None)
    if attr is None:
        pytest.fail(f"Missing attribute required by citation-graph tests: {attr_name}")
    return attr


def build_related_paper(
    *,
    title: str,
    source_paper_id: str,
    source_url: str,
    pdf_url: str,
    doi: str | None = None,
    year: int = 2024,
    authors: list[str] | None = None,
) -> dict[str, object]:
    return {
        "title": title,
        "authors": authors or ["Ada Lovelace"],
        "year": year,
        "abstract": f"Abstract for {title}.",
        "doi": doi,
        "source": "semantic_scholar",
        "source_paper_id": source_paper_id,
        "source_url": source_url,
        "pdf_url": pdf_url,
    }


async def create_citation_paper(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    project_id: str,
    title: str,
    source: str,
    source_paper_id: str | None,
    source_url: str | None,
    doi: str | None,
    pdf_url: str | None = "https://papers.example.com/paper.pdf",
) -> Paper:
    async with session_factory() as session:
        paper = Paper(
            project_id=project_id,
            title=title,
            authors=["Ada Lovelace", "Grace Hopper"],
            year=2024,
            abstract=f"{title} abstract for citation graph tests.",
            doi=doi,
            source=source,
            source_paper_id=source_paper_id,
            source_url=source_url,
            pdf_url=pdf_url,
            status="summarized",
            relevance_score=91.5,
        )
        session.add(paper)
        await session.commit()
        await session.refresh(paper)
        return paper


class FakeSemanticScholarCitationClient:
    def __init__(
        self,
        *,
        paper_details: Any,
        cited_by: list[dict[str, object]],
        references: list[dict[str, object]],
    ) -> None:
        self.paper_details = paper_details
        self.cited_by = cited_by
        self.references = references
        self.detail_calls: list[str] = []
        self.citation_calls: list[tuple[str, int]] = []
        self.reference_calls: list[tuple[str, int]] = []

    async def get_paper_details(self, paper_identifier: str) -> Any:
        self.detail_calls.append(paper_identifier)
        return self.paper_details

    async def get_paper_citations(
        self,
        paper_identifier: str,
        *,
        limit: int,
    ) -> list[dict[str, object]]:
        self.citation_calls.append((paper_identifier, limit))
        return self.cited_by

    async def get_paper_references(
        self,
        paper_identifier: str,
        *,
        limit: int,
    ) -> list[dict[str, object]]:
        self.reference_calls.append((paper_identifier, limit))
        return self.references


class FakePaperCitationService:
    def __init__(
        self,
        *,
        payload: Any | None = None,
        error: Exception | None = None,
    ) -> None:
        self.payload = payload
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def get_citation_graph(
        self,
        *,
        session: AsyncSession,
        paper: Paper,
        limit: int,
    ) -> Any:
        del session
        self.calls.append({"paper": paper, "limit": limit})
        if self.error is not None:
            raise self.error
        if self.payload is None:
            pytest.fail("FakePaperCitationService requires a payload for success-path tests.")
        return self.payload


@pytest.mark.asyncio
async def test_paper_citation_service_returns_graph_for_semantic_scholar_paper(
    session_factory: async_sessionmaker[AsyncSession],
    sample_project: dict[str, str],
) -> None:
    paper_citations = require_module("backend.services.paper_citations")
    semantic_scholar = require_module("backend.services.semantic_scholar")
    service_class = require_attr(paper_citations, "PaperCitationService")
    details_class = require_attr(semantic_scholar, "SemanticScholarPaperDetails")

    paper = await create_citation_paper(
        session_factory,
        project_id=sample_project["id"],
        title="Semantic Scholar Citation Graph Paper",
        source="semantic_scholar",
        source_paper_id="SEM-001",
        source_url="https://www.semanticscholar.org/paper/SEM-001",
        doi="10.1000/semantic-graph",
    )
    client = FakeSemanticScholarCitationClient(
        paper_details=details_class(
            paper_id="SEM-001",
            title=paper.title,
            authors=["Ada Lovelace", "Grace Hopper"],
            year=2024,
            abstract=paper.abstract or "",
            doi=paper.doi,
            source="semantic_scholar",
            source_paper_id="SEM-001",
            source_url="https://www.semanticscholar.org/paper/SEM-001",
            pdf_url="https://pdf.example.com/sem-001.pdf",
            citation_count=7,
            reference_count=3,
        ),
        cited_by=[
            build_related_paper(
                title="Citing Paper One",
                source_paper_id="SEM-CITE-1",
                source_url="https://www.semanticscholar.org/paper/SEM-CITE-1",
                pdf_url="https://pdf.example.com/sem-cite-1.pdf",
            ),
            build_related_paper(
                title="Citing Paper Two",
                source_paper_id="SEM-CITE-2",
                source_url="https://www.semanticscholar.org/paper/SEM-CITE-2",
                pdf_url="https://pdf.example.com/sem-cite-2.pdf",
            ),
        ],
        references=[
            build_related_paper(
                title="Reference Paper One",
                source_paper_id="SEM-REF-1",
                source_url="https://www.semanticscholar.org/paper/SEM-REF-1",
                pdf_url="https://pdf.example.com/sem-ref-1.pdf",
            ),
            build_related_paper(
                title="Reference Paper Two",
                source_paper_id="SEM-REF-2",
                source_url="https://www.semanticscholar.org/paper/SEM-REF-2",
                pdf_url="https://pdf.example.com/sem-ref-2.pdf",
            ),
        ],
    )
    service = service_class(semantic_scholar_client=client)

    async with session_factory() as session:
        loaded_paper = await session.get(Paper, paper.id)
        assert loaded_paper is not None
        result = await service.get_citation_graph(session=session, paper=loaded_paper, limit=2)

    assert result.paper_id == paper.id
    assert result.resolved_by == "semantic_scholar_paper_id"
    assert result.resolved_source_paper_id == "SEM-001"
    assert result.citation_count == 7
    assert result.reference_count == 3
    assert [item["title"] for item in result.cited_by] == ["Citing Paper One", "Citing Paper Two"]
    assert [item["title"] for item in result.references] == [
        "Reference Paper One",
        "Reference Paper Two",
    ]
    assert client.detail_calls == ["SEM-001"]
    assert client.citation_calls == [("SEM-001", 2)]
    assert client.reference_calls == [("SEM-001", 2)]


@pytest.mark.asyncio
async def test_paper_citation_service_resolves_arxiv_backed_paper_via_semantic_scholar(
    session_factory: async_sessionmaker[AsyncSession],
    sample_project: dict[str, str],
) -> None:
    paper_citations = require_module("backend.services.paper_citations")
    semantic_scholar = require_module("backend.services.semantic_scholar")
    service_class = require_attr(paper_citations, "PaperCitationService")
    details_class = require_attr(semantic_scholar, "SemanticScholarPaperDetails")

    paper = await create_citation_paper(
        session_factory,
        project_id=sample_project["id"],
        title="arXiv Citation Graph Paper",
        source="arxiv",
        source_paper_id="2401.12345v1",
        source_url="http://arxiv.org/abs/2401.12345v1",
        doi="10.1000/arxiv-graph",
        pdf_url="http://arxiv.org/pdf/2401.12345v1",
    )
    client = FakeSemanticScholarCitationClient(
        paper_details=details_class(
            paper_id="SEM-ARXIV-001",
            title=paper.title,
            authors=["Ada Lovelace", "Grace Hopper"],
            year=2024,
            abstract=paper.abstract or "",
            doi=paper.doi,
            source="semantic_scholar",
            source_paper_id="SEM-ARXIV-001",
            source_url="https://www.semanticscholar.org/paper/SEM-ARXIV-001",
            pdf_url="https://pdf.example.com/sem-arxiv-001.pdf",
            citation_count=4,
            reference_count=2,
        ),
        cited_by=[
            build_related_paper(
                title="arXiv Citing Paper",
                source_paper_id="SEM-ARXIV-CITE-1",
                source_url="https://www.semanticscholar.org/paper/SEM-ARXIV-CITE-1",
                pdf_url="https://pdf.example.com/sem-arxiv-cite-1.pdf",
            )
        ],
        references=[
            build_related_paper(
                title="arXiv Reference Paper",
                source_paper_id="SEM-ARXIV-REF-1",
                source_url="https://www.semanticscholar.org/paper/SEM-ARXIV-REF-1",
                pdf_url="https://pdf.example.com/sem-arxiv-ref-1.pdf",
            )
        ],
    )
    service = service_class(semantic_scholar_client=client)

    async with session_factory() as session:
        loaded_paper = await session.get(Paper, paper.id)
        assert loaded_paper is not None
        result = await service.get_citation_graph(session=session, paper=loaded_paper, limit=1)

    assert result.paper_id == paper.id
    assert result.resolved_by == "arxiv_id"
    assert result.resolved_source_paper_id == "SEM-ARXIV-001"
    assert result.citation_count == 4
    assert result.reference_count == 2
    assert [item["title"] for item in result.cited_by] == ["arXiv Citing Paper"]
    assert [item["title"] for item in result.references] == ["arXiv Reference Paper"]
    assert client.detail_calls == ["ARXIV:2401.12345v1"]
    assert client.citation_calls == [("SEM-ARXIV-001", 1)]
    assert client.reference_calls == [("SEM-ARXIV-001", 1)]


@pytest.mark.asyncio
async def test_get_paper_citation_graph_returns_semantic_scholar_payload(
    app,
    client,
    auth_headers: dict[str, str],
    sample_project: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    dependencies = require_module("backend.api.dependencies")
    paper_citations = require_module("backend.services.paper_citations")
    dependency = require_attr(dependencies, "get_paper_citation_service")
    result_class = require_attr(paper_citations, "CitationGraphResult")

    paper = await create_citation_paper(
        session_factory,
        project_id=sample_project["id"],
        title="Citation Graph Route Paper",
        source="semantic_scholar",
        source_paper_id="SEM-ROUTE-001",
        source_url="https://www.semanticscholar.org/paper/SEM-ROUTE-001",
        doi="10.1000/route-paper",
    )
    service = FakePaperCitationService(
        payload=result_class(
            paper_id=paper.id,
            resolved_by="semantic_scholar_paper_id",
            resolved_source_paper_id="SEM-ROUTE-001",
            citation_count=2,
            reference_count=1,
            cited_by=[
                build_related_paper(
                    title="Route Citing Paper One",
                    source_paper_id="SEM-ROUTE-CITE-1",
                    source_url="https://www.semanticscholar.org/paper/SEM-ROUTE-CITE-1",
                    pdf_url="https://pdf.example.com/sem-route-cite-1.pdf",
                ),
                build_related_paper(
                    title="Route Citing Paper Two",
                    source_paper_id="SEM-ROUTE-CITE-2",
                    source_url="https://www.semanticscholar.org/paper/SEM-ROUTE-CITE-2",
                    pdf_url="https://pdf.example.com/sem-route-cite-2.pdf",
                ),
            ],
            references=[
                build_related_paper(
                    title="Route Reference Paper",
                    source_paper_id="SEM-ROUTE-REF-1",
                    source_url="https://www.semanticscholar.org/paper/SEM-ROUTE-REF-1",
                    pdf_url="https://pdf.example.com/sem-route-ref-1.pdf",
                )
            ],
        )
    )
    app.dependency_overrides[dependency] = lambda: service

    response = await client.get(
        f"/projects/{sample_project['id']}/papers/{paper.id}/citation-graph?limit=2",
        headers=auth_headers,
    )
    app.dependency_overrides.pop(dependency, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["paper_id"] == paper.id
    assert payload["resolved_by"] == "semantic_scholar_paper_id"
    assert payload["resolved_source_paper_id"] == "SEM-ROUTE-001"
    assert payload["citation_count"] == 2
    assert payload["reference_count"] == 1
    assert [item["title"] for item in payload["cited_by"]] == [
        "Route Citing Paper One",
        "Route Citing Paper Two",
    ]
    assert [item["title"] for item in payload["references"]] == ["Route Reference Paper"]
    assert len(service.calls) == 1
    assert service.calls[0]["paper"].id == paper.id
    assert service.calls[0]["limit"] == 2


@pytest.mark.asyncio
async def test_get_paper_citation_graph_returns_arxiv_backed_payload(
    app,
    client,
    auth_headers: dict[str, str],
    sample_project: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    dependencies = require_module("backend.api.dependencies")
    paper_citations = require_module("backend.services.paper_citations")
    dependency = require_attr(dependencies, "get_paper_citation_service")
    result_class = require_attr(paper_citations, "CitationGraphResult")

    paper = await create_citation_paper(
        session_factory,
        project_id=sample_project["id"],
        title="arXiv Route Paper",
        source="arxiv",
        source_paper_id="2401.55555v1",
        source_url="http://arxiv.org/abs/2401.55555v1",
        doi="10.1000/arxiv-route-paper",
        pdf_url="http://arxiv.org/pdf/2401.55555v1",
    )
    service = FakePaperCitationService(
        payload=result_class(
            paper_id=paper.id,
            resolved_by="arxiv_id",
            resolved_source_paper_id="SEM-ARXIV-ROUTE-001",
            citation_count=1,
            reference_count=1,
            cited_by=[
                build_related_paper(
                    title="Resolved arXiv Citation",
                    source_paper_id="SEM-ARXIV-ROUTE-CITE-1",
                    source_url="https://www.semanticscholar.org/paper/SEM-ARXIV-ROUTE-CITE-1",
                    pdf_url="https://pdf.example.com/sem-arxiv-route-cite-1.pdf",
                )
            ],
            references=[
                build_related_paper(
                    title="Resolved arXiv Reference",
                    source_paper_id="SEM-ARXIV-ROUTE-REF-1",
                    source_url="https://www.semanticscholar.org/paper/SEM-ARXIV-ROUTE-REF-1",
                    pdf_url="https://pdf.example.com/sem-arxiv-route-ref-1.pdf",
                )
            ],
        )
    )
    app.dependency_overrides[dependency] = lambda: service

    response = await client.get(
        f"/projects/{sample_project['id']}/papers/{paper.id}/citation-graph?limit=1",
        headers=auth_headers,
    )
    app.dependency_overrides.pop(dependency, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["paper_id"] == paper.id
    assert payload["resolved_by"] == "arxiv_id"
    assert payload["resolved_source_paper_id"] == "SEM-ARXIV-ROUTE-001"
    assert payload["citation_count"] == 1
    assert payload["reference_count"] == 1
    assert [item["title"] for item in payload["cited_by"]] == ["Resolved arXiv Citation"]
    assert [item["title"] for item in payload["references"]] == ["Resolved arXiv Reference"]
    assert len(service.calls) == 1
    assert service.calls[0]["paper"].id == paper.id
    assert service.calls[0]["limit"] == 1


@pytest.mark.asyncio
async def test_get_paper_citation_graph_returns_400_for_unresolved_uploaded_paper(
    app,
    client,
    auth_headers: dict[str, str],
    sample_project: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    dependencies = require_module("backend.api.dependencies")
    paper_citations = require_module("backend.services.paper_citations")
    dependency = require_attr(dependencies, "get_paper_citation_service")
    error_class = require_attr(paper_citations, "CitationResolutionError")

    paper = await create_citation_paper(
        session_factory,
        project_id=sample_project["id"],
        title="Uploaded Local Paper",
        source="user_upload",
        source_paper_id=None,
        source_url=None,
        doi=None,
    )
    service = FakePaperCitationService(
        error=error_class(
            "Paper cannot be resolved exactly to Semantic Scholar. "
            "A Semantic Scholar id, arXiv id, or DOI is required."
        )
    )
    app.dependency_overrides[dependency] = lambda: service

    response = await client.get(
        f"/projects/{sample_project['id']}/papers/{paper.id}/citation-graph",
        headers=auth_headers,
    )
    app.dependency_overrides.pop(dependency, None)

    assert response.status_code == 400
    assert response.json() == {
        "detail": (
            "Paper cannot be resolved exactly to Semantic Scholar. "
            "A Semantic Scholar id, arXiv id, or DOI is required."
        )
    }


@pytest.mark.asyncio
async def test_get_paper_citation_graph_returns_404_for_missing_project_paper(
    client,
    auth_headers: dict[str, str],
    sample_project: dict[str, str],
) -> None:
    response = await client.get(
        f"/projects/{sample_project['id']}/papers/missing-paper-id/citation-graph",
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Paper not found."}


@pytest.mark.asyncio
async def test_get_paper_citation_graph_returns_404_when_upstream_exact_match_is_missing(
    app,
    client,
    auth_headers: dict[str, str],
    sample_project: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    dependencies = require_module("backend.api.dependencies")
    paper_citations = require_module("backend.services.paper_citations")
    dependency = require_attr(dependencies, "get_paper_citation_service")
    error_class = require_attr(paper_citations, "CitationNotFoundError")

    paper = await create_citation_paper(
        session_factory,
        project_id=sample_project["id"],
        title="Missing Upstream Match Paper",
        source="semantic_scholar",
        source_paper_id="SEM-MISS-001",
        source_url="https://www.semanticscholar.org/paper/SEM-MISS-001",
        doi="10.1000/missing-upstream",
    )
    service = FakePaperCitationService(
        error=error_class("Exact paper was not found in Semantic Scholar.")
    )
    app.dependency_overrides[dependency] = lambda: service

    response = await client.get(
        f"/projects/{sample_project['id']}/papers/{paper.id}/citation-graph",
        headers=auth_headers,
    )
    app.dependency_overrides.pop(dependency, None)

    assert response.status_code == 404
    assert response.json() == {"detail": "Exact paper was not found in Semantic Scholar."}


@pytest.mark.asyncio
async def test_get_paper_citation_graph_returns_502_on_upstream_failure(
    app,
    client,
    auth_headers: dict[str, str],
    sample_project: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    dependencies = require_module("backend.api.dependencies")
    paper_citations = require_module("backend.services.paper_citations")
    dependency = require_attr(dependencies, "get_paper_citation_service")
    error_class = require_attr(paper_citations, "CitationProviderError")

    paper = await create_citation_paper(
        session_factory,
        project_id=sample_project["id"],
        title="Upstream Failure Paper",
        source="semantic_scholar",
        source_paper_id="SEM-UPSTREAM-001",
        source_url="https://www.semanticscholar.org/paper/SEM-UPSTREAM-001",
        doi="10.1000/upstream-failure",
    )
    service = FakePaperCitationService(
        error=error_class("Semantic Scholar request failed.")
    )
    app.dependency_overrides[dependency] = lambda: service

    response = await client.get(
        f"/projects/{sample_project['id']}/papers/{paper.id}/citation-graph",
        headers=auth_headers,
    )
    app.dependency_overrides.pop(dependency, None)

    assert response.status_code == 502
    assert response.json() == {"detail": "Semantic Scholar request failed."}


@pytest.mark.asyncio
async def test_get_paper_citation_graph_validates_limit_bounds(
    app,
    client,
    auth_headers: dict[str, str],
    sample_project: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    dependencies = require_module("backend.api.dependencies")
    paper_citations = require_module("backend.services.paper_citations")
    dependency = require_attr(dependencies, "get_paper_citation_service")
    result_class = require_attr(paper_citations, "CitationGraphResult")

    paper = await create_citation_paper(
        session_factory,
        project_id=sample_project["id"],
        title="Limit Validation Paper",
        source="semantic_scholar",
        source_paper_id="SEM-LIMIT-001",
        source_url="https://www.semanticscholar.org/paper/SEM-LIMIT-001",
        doi="10.1000/limit-validation",
    )
    service = FakePaperCitationService(
        payload=result_class(
            paper_id=paper.id,
            resolved_by="semantic_scholar_paper_id",
            resolved_source_paper_id="SEM-LIMIT-001",
            citation_count=0,
            reference_count=0,
            cited_by=[],
            references=[],
        )
    )
    app.dependency_overrides[dependency] = lambda: service

    too_small_response = await client.get(
        f"/projects/{sample_project['id']}/papers/{paper.id}/citation-graph?limit=0",
        headers=auth_headers,
    )
    too_large_response = await client.get(
        f"/projects/{sample_project['id']}/papers/{paper.id}/citation-graph?limit=101",
        headers=auth_headers,
    )
    valid_response = await client.get(
        f"/projects/{sample_project['id']}/papers/{paper.id}/citation-graph?limit=1",
        headers=auth_headers,
    )
    app.dependency_overrides.pop(dependency, None)

    assert too_small_response.status_code == 422
    assert too_large_response.status_code == 422
    assert valid_response.status_code == 200
    assert len(service.calls) == 1
    assert service.calls[0]["limit"] == 1
