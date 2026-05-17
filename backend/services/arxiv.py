import re

import feedparser
import httpx

from backend.services.paper_types import PaperRecord

ARXIV_URL = "https://export.arxiv.org/api/query"
ARXIV_PDF_BASE = "https://arxiv.org/pdf/"
ARXIV_ID_PATTERN = re.compile(r"(?:arxiv\.org/(?:abs|pdf)/)(\d{4}\.\d{4,5}(?:v\d+)?)")


class ArxivUnavailable(RuntimeError):
    """Raised when arXiv is transiently unavailable (timeouts, rate limits).

    Callers that have a fallback source (e.g. Tavily) should treat this as
    expected and skip surfacing it as a user-facing warning.
    """


def coerce_optional_string(value: object) -> str | None:
    """Normalize optional provider string values."""

    if value is None:
        return None

    normalized_value = str(value).strip()
    return normalized_value or None


def extract_arxiv_identifier(source_url: str | None) -> str | None:
    """Extract the arXiv identifier from the source URL when possible."""

    if source_url is None or "/abs/" not in source_url:
        return None

    return source_url.rsplit("/abs/", maxsplit=1)[-1].strip() or None


def extract_pdf_url(entry: dict[str, object], source_url: str | None) -> str | None:
    """Resolve the PDF URL from entry metadata or derive it from the abstract URL."""

    raw_links = entry.get("links", [])
    if isinstance(raw_links, list):
        for raw_link in raw_links:
            if not isinstance(raw_link, dict):
                continue

            href = coerce_optional_string(raw_link.get("href"))
            link_title = str(raw_link.get("title", "")).strip().lower()
            link_type = str(raw_link.get("type", "")).strip().lower()
            if href is None:
                continue
            if link_title == "pdf" or link_type == "application/pdf":
                return href

    if source_url is None or "/abs/" not in source_url:
        return None

    return source_url.replace("/abs/", "/pdf/", 1)


def normalize_arxiv_entry(entry: dict[str, object]) -> PaperRecord:
    """Normalize an arXiv Atom entry into the shared paper schema."""

    raw_authors = entry.get("authors", [])
    authors = raw_authors if isinstance(raw_authors, list) else []
    published = str(entry.get("published", ""))
    year = int(published[:4]) if len(published) >= 4 and published[:4].isdigit() else None
    source_url = coerce_optional_string(entry.get("id"))

    normalized_paper: PaperRecord = {
        "title": str(entry.get("title", "")).replace("\n", " ").strip(),
        "authors": [
            str(author.get("name", "")).strip() for author in authors if isinstance(author, dict)
        ],
        "year": year,
        "abstract": str(entry.get("summary", "")).replace("\n", " ").strip(),
        "doi": coerce_optional_string(entry.get("arxiv_doi")),
        "source": "arxiv",
        "source_paper_id": extract_arxiv_identifier(source_url),
        "source_url": source_url,
        "pdf_url": extract_pdf_url(entry, source_url),
        "citation_count": None,
        "reference_count": None,
        "relevance_score": None,
    }
    return normalized_paper


async def download_pdf(
    arxiv_id_or_url: str,
    http_client: httpx.AsyncClient | None = None,
) -> bytes:
    """Fetch an arXiv PDF by ID or URL; returns raw bytes."""

    normalized = arxiv_id_or_url.strip()
    match = ARXIV_ID_PATTERN.search(normalized)
    if match:
        arxiv_id = match.group(1)
    else:
        arxiv_id = normalized.split("/")[-1].strip()

    pdf_url = f"{ARXIV_PDF_BASE}{arxiv_id}"
    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=60.0, follow_redirects=True)

    try:
        response = await client.get(pdf_url)
        response.raise_for_status()
        return response.content
    except httpx.HTTPError as error:
        raise RuntimeError(f"arXiv PDF download failed for '{arxiv_id}'.") from error
    finally:
        if owns_client:
            await client.aclose()


async def search_papers(
    query: str,
    year_start: int,
    limit: int,
    http_client: httpx.AsyncClient | None = None,
) -> list[PaperRecord]:
    """Search arXiv and return normalized paper payloads."""

    params: dict[str, str | int] = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": limit,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=45.0, follow_redirects=True)

    try:
        response = await client.get(ARXIV_URL, params=params)
        response.raise_for_status()
    except httpx.TimeoutException as error:
        raise ArxivUnavailable(f"timeout ({type(error).__name__})") from error
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 429:
            raise ArxivUnavailable("rate limited (HTTP 429)") from error
        raise RuntimeError(f"HTTP {error.response.status_code}") from error
    except httpx.HTTPError as error:
        detail = str(error) or repr(error)
        raise RuntimeError(f"HTTP {type(error).__name__}: {detail}") from error
    finally:
        if owns_client:
            await client.aclose()

    feed = feedparser.parse(response.text)
    papers: list[PaperRecord] = []
    for raw_entry in feed.entries:
        entry = normalize_arxiv_entry(dict(raw_entry))
        if entry["year"] is None or entry["year"] >= year_start:
            papers.append(entry)

    return papers
