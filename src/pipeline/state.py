"""
Shared pipeline state — Pydantic models used across all pipeline stages.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from pydantic import BaseModel


class PaperCandidate(BaseModel):
    """A paper candidate flowing through the pipeline."""

    # Identity
    id: str = ""  # source-specific ID (e.g., arxiv:2301.12345)
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    title: str = ""
    authors: list[str] = []

    # Content
    abstract: str = ""
    pdf_url: Optional[str] = None

    # Metadata
    source: str = ""  # semantic_scholar | arxiv | pubmed | local_index
    year: Optional[int] = None
    citation_count: int = 0
    categories: list[str] = []

    # Pipeline scores (populated in stages 2-3)
    relevance_score: float = 0.0  # cosine similarity (stage 2)
    composite_score: float = 0.0  # weighted score (stage 3)

    # Summary (populated in stage 4)
    summary: str = ""


class QualityScores(BaseModel):
    """Quality assessment from Stage 5."""

    coherence: float = 0.0
    coverage: float = 0.0
    citation_accuracy: float = 0.0
    writing_quality: float = 0.0
    feedback: str = ""

    @property
    def average(self) -> float:
        return (self.coherence + self.coverage + self.citation_accuracy + self.writing_quality) / 4


class ReviewSection(BaseModel):
    """A section of the generated literature review."""

    heading: str = ""
    content: str = ""


@dataclass
class PipelineState:
    """Shared mutable state passed through all LangGraph nodes.

    LangGraph requires the state to be a TypedDict or dataclass.
    """

    # --- Input (set by user) ---
    topic: str = ""
    constraints: dict = field(default_factory=dict)
    # constraints schema:
    # {
    #   "year_min": int,
    #   "year_max": int,
    #   "categories": list[str],
    #   "max_papers": int,
    #   "keywords": list[str],
    #   "output_formats": list[str],
    # }

    # --- Stage 1: Search output ---
    candidates: list[PaperCandidate] = field(default_factory=list)

    # --- Stage 2: Filter output ---
    filtered: list[PaperCandidate] = field(default_factory=list)

    # --- Stage 3: Rank output ---
    ranked: list[PaperCandidate] = field(default_factory=list)

    # --- Stage 4: Synthesis output ---
    sections: list[ReviewSection] = field(default_factory=list)
    full_text: str = ""
    bibliography: list[str] = field(default_factory=list)  # formatted references

    # --- Stage 5: Quality output ---
    quality_scores: QualityScores = field(default_factory=QualityScores)
    quality_approved: bool = False
    quality_retries: int = 0

    # --- Pipeline metadata ---
    review_id: int | None = None  # DB review ID
    user_id: int | None = None
    status: str = "pending"
    error: str | None = None

    # --- Output file paths (after generation) ---
    output_files: dict = field(default_factory=dict)  # {"docx": bytes, "tex": bytes, "pdf": bytes}
