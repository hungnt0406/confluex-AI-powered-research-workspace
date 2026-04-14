from typing import Literal, TypedDict

PaperStatus = Literal["candidate", "ranked", "summarized", "summary_error"]


class PaperRecord(TypedDict):
    """Normalized paper payload shared by all search clients."""

    title: str
    authors: list[str]
    year: int | None
    abstract: str
    doi: str | None
    source: str
    source_paper_id: str | None
    source_url: str | None
    pdf_url: str | None
    relevance_score: float | None
