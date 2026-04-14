import asyncio

import httpx

from backend.config import get_settings
from backend.services.paper_types import PaperRecord

SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1/paper/search"


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

    year: int | None = None
    if isinstance(raw_year, int):
        year = raw_year
    elif isinstance(raw_year, str) and raw_year.isdigit():
        year = int(raw_year)

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
        "relevance_score": None,
    }
    return normalized_paper


async def search_papers(
    query: str,
    year_start: int,
    limit: int,
    http_client: httpx.AsyncClient | None = None,
) -> list[PaperRecord]:
    """Search Semantic Scholar papers with a normalized response shape."""

    settings = get_settings()
    headers: dict[str, str] = {}
    if settings.semantic_scholar_api_key:
        headers["x-api-key"] = settings.semantic_scholar_api_key

    params: dict[str, str | int] = {
        "query": query,
        "limit": limit,
        "year": f"{year_start}-",
        "fields": "paperId,url,openAccessPdf,title,authors,year,abstract,externalIds",
    }

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=15.0)

    try:
        async with request_limiter:
            response = await client.get(SEMANTIC_SCHOLAR_URL, params=params, headers=headers)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise RuntimeError("Semantic Scholar search failed.") from error
    finally:
        if owns_client:
            await client.aclose()

    payload = response.json()
    raw_papers = payload.get("data", [])
    if not isinstance(raw_papers, list):
        return []

    return [
        normalize_paper_payload(raw_paper)
        for raw_paper in raw_papers
        if isinstance(raw_paper, dict)
    ]
