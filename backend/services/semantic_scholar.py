import asyncio
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from backend.config import get_settings
from backend.services.paper_types import PaperRecord

SEMANTIC_SCHOLAR_GRAPH_URL = "https://api.semanticscholar.org/graph/v1"
SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
SEMANTIC_SCHOLAR_PAPER_FIELDS = (
    "paperId,url,openAccessPdf,title,authors,year,abstract,externalIds,"
    "citationCount,referenceCount"
)
SEMANTIC_SCHOLAR_CITATION_FIELDS = (
    "citingPaper.paperId,citingPaper.url,citingPaper.openAccessPdf,"
    "citingPaper.title,citingPaper.authors,citingPaper.year,"
    "citingPaper.abstract,citingPaper.externalIds"
)
SEMANTIC_SCHOLAR_REFERENCE_FIELDS = (
    "citedPaper.paperId,citedPaper.url,citedPaper.openAccessPdf,"
    "citedPaper.title,citedPaper.authors,citedPaper.year,"
    "citedPaper.abstract,citedPaper.externalIds"
)


class RequestWindowLimiter:
    """Rate-limit requests by holding semaphore permits for a full interval."""

    def __init__(self, max_requests: int, interval_seconds: float):
        self.semaphore = asyncio.Semaphore(max_requests)
        self.interval_seconds = interval_seconds

    async def __aenter__(self) -> None:
        await self.semaphore.acquire()

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        loop = asyncio.get_running_loop()
        loop.call_later(self.interval_seconds, self.semaphore.release)


request_limiter = RequestWindowLimiter(max_requests=3, interval_seconds=1.0)


class SemanticScholarProviderError(RuntimeError):
    """Raised when Semantic Scholar fails unexpectedly."""


class SemanticScholarPaperLookupError(SemanticScholarProviderError):
    """Raised when the caller provides an unsupported paper lookup identifier."""


class SemanticScholarPaperNotFoundError(SemanticScholarProviderError):
    """Raised when Semantic Scholar cannot find the requested paper."""


@dataclass(frozen=True)
class SemanticScholarPaperDetails:
    """Normalized paper detail payload used for citation graph resolution."""

    paper_id: str
    title: str
    authors: list[str]
    year: int | None
    abstract: str
    doi: str | None
    source: str
    source_paper_id: str | None
    source_url: str | None
    pdf_url: str | None
    citation_count: int | None
    reference_count: int | None


def coerce_optional_string(value: object) -> str | None:
    """Normalize optional provider string values."""

    if value is None:
        return None

    normalized_value = str(value).strip()
    return normalized_value or None


def normalize_paper_payload(raw_paper: dict[str, object]) -> PaperRecord:
    """Normalize Semantic Scholar results into the shared paper schema."""

    raw_authors = raw_paper.get("authors", [])
    authors = raw_authors if isinstance(raw_authors, list) else []
    raw_external_ids = raw_paper.get("externalIds", {})
    external_ids = raw_external_ids if isinstance(raw_external_ids, dict) else {}
    raw_open_access_pdf = raw_paper.get("openAccessPdf", {})
    open_access_pdf = raw_open_access_pdf if isinstance(raw_open_access_pdf, dict) else {}
    raw_year = raw_paper.get("year")
    raw_citation_count = raw_paper.get("citationCount")
    raw_reference_count = raw_paper.get("referenceCount")

    year: int | None = None
    if isinstance(raw_year, int):
        year = raw_year
    elif isinstance(raw_year, str) and raw_year.isdigit():
        year = int(raw_year)

    citation_count = raw_citation_count if isinstance(raw_citation_count, int) else None
    reference_count = raw_reference_count if isinstance(raw_reference_count, int) else None

    normalized_paper: PaperRecord = {
        "title": str(raw_paper.get("title", "")).strip(),
        "authors": [
            str(author.get("name", "")).strip() for author in authors if isinstance(author, dict)
        ],
        "year": year,
        "abstract": str(raw_paper.get("abstract", "")).strip(),
        "doi": coerce_optional_string(external_ids.get("DOI")),
        "source": "semantic_scholar",
        "source_paper_id": coerce_optional_string(raw_paper.get("paperId")),
        "source_url": coerce_optional_string(raw_paper.get("url")),
        "pdf_url": coerce_optional_string(open_access_pdf.get("url")),
        "citation_count": citation_count,
        "reference_count": reference_count,
        "relevance_score": None,
    }
    return normalized_paper


def normalize_paper_details_payload(raw_paper: dict[str, object]) -> SemanticScholarPaperDetails:
    """Normalize Semantic Scholar paper details into a richer payload."""

    normalized_paper = normalize_paper_payload(raw_paper)
    return SemanticScholarPaperDetails(
        paper_id=str(raw_paper.get("paperId", "")).strip(),
        title=normalized_paper["title"],
        authors=list(normalized_paper["authors"]),
        year=normalized_paper["year"],
        abstract=normalized_paper["abstract"],
        doi=normalized_paper["doi"],
        source=normalized_paper["source"],
        source_paper_id=normalized_paper["source_paper_id"],
        source_url=normalized_paper["source_url"],
        pdf_url=normalized_paper["pdf_url"],
        citation_count=normalized_paper["citation_count"],
        reference_count=normalized_paper["reference_count"],
    )


def normalize_related_paper_payload(
    raw_entry: dict[str, object],
    *,
    nested_key: str,
) -> dict[str, object]:
    """Normalize citation/reference payloads into a shared related-paper shape."""

    nested_paper = raw_entry.get(nested_key)
    if not isinstance(nested_paper, dict):
        raise SemanticScholarProviderError(
            f"Semantic Scholar {nested_key} payload was missing the nested paper object."
        )

    normalized_paper = normalize_paper_payload(nested_paper)
    return {
        "title": normalized_paper["title"],
        "authors": list(normalized_paper["authors"]),
        "year": normalized_paper["year"],
        "abstract": normalized_paper["abstract"] or None,
        "doi": normalized_paper["doi"],
        "source": normalized_paper["source"],
        "source_paper_id": normalized_paper["source_paper_id"],
        "source_url": normalized_paper["source_url"],
        "pdf_url": normalized_paper["pdf_url"],
    }


def build_headers() -> dict[str, str]:
    """Build Semantic Scholar headers from settings."""

    settings = get_settings()
    headers: dict[str, str] = {}
    if settings.semantic_scholar_api_key:
        headers["x-api-key"] = settings.semantic_scholar_api_key
    return headers


async def execute_request(
    *,
    method: str,
    url: str,
    params: dict[str, str | int] | None = None,
    headers: dict[str, str] | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> dict[str, object]:
    """Execute a Semantic Scholar request and return the JSON payload."""

    settings = get_settings()
    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=settings.external_api_timeout_seconds)

    try:
        async with request_limiter:
            response = await client.request(
                method,
                url,
                params=params,
                headers=headers,
            )
        if response.status_code == 400:
            raise SemanticScholarPaperLookupError(
                "Semantic Scholar rejected the paper identifier for exact lookup."
            )
        if response.status_code == 404:
            raise SemanticScholarPaperNotFoundError(
                "Semantic Scholar could not find the requested paper."
            )
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise SemanticScholarProviderError("Semantic Scholar request failed.") from error
    finally:
        if owns_client:
            await client.aclose()

    payload = response.json()
    if not isinstance(payload, dict):
        raise SemanticScholarProviderError("Semantic Scholar returned an invalid JSON payload.")
    return payload


async def search_papers(
    query: str,
    year_start: int,
    limit: int,
    http_client: httpx.AsyncClient | None = None,
) -> list[PaperRecord]:
    """Search Semantic Scholar papers with a normalized response shape."""

    params: dict[str, str | int] = {
        "query": query,
        "limit": limit,
        "year": f"{year_start}-",
        "fields": SEMANTIC_SCHOLAR_PAPER_FIELDS,
    }
    payload = await execute_request(
        method="GET",
        url=SEMANTIC_SCHOLAR_URL,
        params=params,
        headers=build_headers(),
        http_client=http_client,
    )
    raw_papers = payload.get("data", [])
    if not isinstance(raw_papers, list):
        return []

    return [
        normalize_paper_payload(raw_paper)
        for raw_paper in raw_papers
        if isinstance(raw_paper, dict)
    ]


async def get_paper_details(
    paper_identifier: str,
    http_client: httpx.AsyncClient | None = None,
) -> SemanticScholarPaperDetails:
    """Resolve one exact Semantic Scholar paper by provider-supported identifier."""

    normalized_identifier = paper_identifier.strip()
    if not normalized_identifier:
        raise SemanticScholarPaperLookupError("Semantic Scholar paper identifier must not be empty.")

    payload = await execute_request(
        method="GET",
        url=f"{SEMANTIC_SCHOLAR_GRAPH_URL}/paper/{quote(normalized_identifier, safe='')}",
        params={"fields": SEMANTIC_SCHOLAR_PAPER_FIELDS},
        headers=build_headers(),
        http_client=http_client,
    )
    paper_id = str(payload.get("paperId", "")).strip()
    if not paper_id:
        raise SemanticScholarProviderError(
            "Semantic Scholar paper details response did not include paperId."
        )

    return normalize_paper_details_payload(payload)


async def get_paper_citations(
    paper_identifier: str,
    *,
    limit: int,
    http_client: httpx.AsyncClient | None = None,
) -> list[dict[str, object]]:
    """Return papers citing the requested Semantic Scholar paper."""

    payload = await execute_request(
        method="GET",
        url=f"{SEMANTIC_SCHOLAR_GRAPH_URL}/paper/{quote(paper_identifier, safe='')}/citations",
        params={
            "fields": SEMANTIC_SCHOLAR_CITATION_FIELDS,
            "limit": limit,
        },
        headers=build_headers(),
        http_client=http_client,
    )
    raw_citations = payload.get("data", [])
    if not isinstance(raw_citations, list):
        return []

    return [
        normalize_related_paper_payload(raw_entry, nested_key="citingPaper")
        for raw_entry in raw_citations
        if isinstance(raw_entry, dict)
    ]


async def get_paper_references(
    paper_identifier: str,
    *,
    limit: int,
    http_client: httpx.AsyncClient | None = None,
) -> list[dict[str, object]]:
    """Return papers referenced by the requested Semantic Scholar paper."""

    payload = await execute_request(
        method="GET",
        url=f"{SEMANTIC_SCHOLAR_GRAPH_URL}/paper/{quote(paper_identifier, safe='')}/references",
        params={
            "fields": SEMANTIC_SCHOLAR_REFERENCE_FIELDS,
            "limit": limit,
        },
        headers=build_headers(),
        http_client=http_client,
    )
    raw_references = payload.get("data", [])
    if not isinstance(raw_references, list):
        return []

    return [
        normalize_related_paper_payload(raw_entry, nested_key="citedPaper")
        for raw_entry in raw_references
        if isinstance(raw_entry, dict)
    ]
