from datetime import datetime
from math import ceil
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProjectCreate(BaseModel):
    """Request body for creating a project."""

    title: str = Field(min_length=1, max_length=255)
    topic_description: str = Field(min_length=1, max_length=4_000)
    citation_format: str = Field(min_length=1, max_length=100)
    year_start: int = Field(default=2018, ge=1900, le=2100)
    candidate_limit: int = Field(default=60, ge=5, le=200)
    summary_limit: int = Field(default=30, ge=1, le=100)

    @model_validator(mode="after")
    def validate_limit_relationships(self) -> "ProjectCreate":
        if self.summary_limit > self.candidate_limit:
            raise ValueError("summary_limit must be less than or equal to candidate_limit.")
        return self


class ProjectRead(BaseModel):
    """Serialized project payload."""

    id: str
    user_id: str
    title: str
    topic_description: str
    citation_format: str
    year_start: int
    candidate_limit: int
    summary_limit: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RunPipelineResponse(BaseModel):
    """Response returned after a project pipeline finishes."""

    status: Literal["completed"]
    project_id: str
    queries: list[str]
    candidate_count: int
    ranked_count: int
    summary_count: int
    qa_flags: list[str]
    errors: list[str]


class PaperSummaryRead(BaseModel):
    """Serialized structured summary for a paper."""

    problem: str | None
    method: str | None
    result: str | None
    relevance_to_topic: str | None
    has_error: bool
    error_message: str | None

    model_config = ConfigDict(from_attributes=True)


class ProjectPaperRead(BaseModel):
    """Serialized paper payload for project-level listings."""

    id: str
    project_id: str
    title: str
    authors: list[str]
    year: int | None
    abstract: str | None
    doi: str | None
    source: str
    status: str
    relevance_score: float | None
    summary: PaperSummaryRead | None

    model_config = ConfigDict(from_attributes=True)


class PaginationMeta(BaseModel):
    """Pagination metadata for collection endpoints."""

    total: int
    page: int
    per_page: int
    total_pages: int

    @classmethod
    def from_totals(cls, *, total: int, page: int, per_page: int) -> "PaginationMeta":
        total_pages = ceil(total / per_page) if total else 0
        return cls(total=total, page=page, per_page=per_page, total_pages=total_pages)


class ProjectPaperListResponse(BaseModel):
    """Paginated collection response for project papers."""

    data: list[ProjectPaperRead]
    meta: PaginationMeta


class PipelineHealthResponse(BaseModel):
    """Health payload for the dummy pipeline graph."""

    status: Literal["ok"]
    nodes: list[str]
