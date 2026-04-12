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
    relevance_score: float | None
