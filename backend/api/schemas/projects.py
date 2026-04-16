from datetime import datetime
from math import ceil
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from backend.db.models import PaperConversation, ReferenceFile


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
    reference_file_id: str | None
    title: str
    authors: list[str]
    year: int | None
    abstract: str | None
    doi: str | None
    source: str
    source_paper_id: str | None
    source_url: str | None
    pdf_url: str | None
    status: str
    relevance_score: float | None
    summary: PaperSummaryRead | None

    model_config = ConfigDict(from_attributes=True)


class ReferenceFileRead(BaseModel):
    """Serialized project reference file metadata."""

    id: str
    project_id: str
    original_filename: str
    content_type: str | None
    byte_size: int
    sha256: str
    parse_status: str
    extracted_title: str | None
    extracted_authors: list[str]
    extracted_year: int | None
    extracted_abstract: str | None
    linked_paper_id: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_reference(cls, reference: "ReferenceFile") -> "ReferenceFileRead":
        paper = reference.paper
        return cls(
            id=reference.id,
            project_id=reference.project_id,
            original_filename=reference.original_filename,
            content_type=reference.content_type,
            byte_size=reference.byte_size,
            sha256=reference.sha256,
            parse_status=reference.parse_status,
            extracted_title=reference.extracted_title,
            extracted_authors=list(reference.extracted_authors),
            extracted_year=reference.extracted_year,
            extracted_abstract=reference.extracted_abstract,
            linked_paper_id=paper.id if paper is not None else None,
            error_message=reference.error_message,
            created_at=reference.created_at,
            updated_at=reference.updated_at,
        )


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


class PaperConversationQuestionCreate(BaseModel):
    """Request body for asking a question in a paper conversation flow."""

    question: str = Field(min_length=1, max_length=8_000)


class PaperConversationCreate(PaperConversationQuestionCreate):
    """Request body for starting a paper conversation."""


class PaperConversationMessageCreate(PaperConversationQuestionCreate):
    """Request body for adding a follow-up turn to a paper conversation."""


class PaperMessageRead(BaseModel):
    """Serialized message payload for a paper conversation."""

    id: str
    conversation_id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaperConversationRead(BaseModel):
    """Serialized paper conversation with its persisted messages."""

    id: str
    paper_id: str
    created_at: datetime
    updated_at: datetime
    messages: list[PaperMessageRead]

    model_config = ConfigDict(from_attributes=True)


class PaperConversationSummaryRead(BaseModel):
    """Serialized paper conversation summary for list views."""

    id: str
    paper_id: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    opening_question: str | None

    @classmethod
    def from_conversation(cls, conversation: "PaperConversation") -> "PaperConversationSummaryRead":
        opening_question = next(
            (message.content for message in conversation.messages if message.role == "user"),
            None,
        )
        return cls(
            id=conversation.id,
            paper_id=conversation.paper_id,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=len(conversation.messages),
            opening_question=opening_question,
        )


class PipelineHealthResponse(BaseModel):
    """Health payload for the dummy pipeline graph."""

    status: Literal["ok"]
    nodes: list[str]
