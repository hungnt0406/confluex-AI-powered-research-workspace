import feedparser
import httpx

from backend.services.paper_types import PaperRecord

ARXIV_URL = "http://export.arxiv.org/api/query"


def normalize_arxiv_entry(entry: dict[str, object]) -> PaperRecord:
    """Normalize an arXiv Atom entry into the shared paper schema."""

    raw_authors = entry.get("authors", [])
    authors = raw_authors if isinstance(raw_authors, list) else []
    published = str(entry.get("published", ""))
    year = int(published[:4]) if len(published) >= 4 and published[:4].isdigit() else None

    return PaperRecord(
        title=str(entry.get("title", "")).replace("\n", " ").strip(),
        authors=[
            str(author.get("name", "")).strip() for author in authors if isinstance(author, dict)
        ],
        year=year,
        abstract=str(entry.get("summary", "")).replace("\n", " ").strip(),
        doi=str(entry["arxiv_doi"]) if entry.get("arxiv_doi") is not None else None,
        source="arxiv",
        relevance_score=None,
    )


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
    client = http_client or httpx.AsyncClient(timeout=15.0)

    try:
        response = await client.get(ARXIV_URL, params=params)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise RuntimeError("arXiv search failed.") from error
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
