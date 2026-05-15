"""Pydantic schemas for the writer workspace endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class WriterDocumentCreate(BaseModel):
    topic: str = Field(min_length=3, max_length=2000)
    thesis: str | None = Field(default=None, max_length=1000)
    title: str = Field(default="Untitled Paper", max_length=500)
    paper_type: str = Field(default="imrad")
    citation_style: str = Field(default="ieee")


class WriterDocumentUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    thesis: str | None = Field(default=None, max_length=1000)
    preamble: str | None = None


class WriterSectionRead(BaseModel):
    id: str
    section_type: str
    order_index: int
    title: str
    outline_text: str | None
    user_inputs_json: dict[str, Any]
    draft_latex: str | None
    low_confidence_spans_json: list[dict[str, Any]]
    cited_paper_ids_json: list[str]
    status: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class WriterSourcePaperRead(BaseModel):
    id: str
    title: str
    authors: list[str]
    year: int | None
    source: str
    source_paper_id: str | None
    source_url: str | None
    pdf_url: str | None
    reference_file_id: str | None

    model_config = {"from_attributes": True}


class WriterDocumentRead(BaseModel):
    id: str
    user_id: str
    project_id: str | None
    title: str
    topic: str
    thesis: str | None
    paper_type: str
    citation_style: str
    preamble: str | None
    source_paper_ids_json: list[str]
    source_papers: list[WriterSourcePaperRead] = Field(default_factory=list)
    status: str
    created_at: datetime
    updated_at: datetime
    sections: list[WriterSectionRead]

    model_config = {"from_attributes": True}


class WriterDocumentSummaryRead(BaseModel):
    id: str
    user_id: str
    project_id: str | None
    title: str
    topic: str
    paper_type: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OutlineProposeResponse(BaseModel):
    outline_by_section: dict[str, str]


class OutlineApplyRequest(BaseModel):
    outline_by_section: dict[str, str] = Field(
        description="Map of section_id -> outline_text"
    )


class SectionOutlineProposeResponse(BaseModel):
    section_id: str
    outline_text: str
    warnings: list[str] = Field(default_factory=list)


class SectionOutlineApplyRequest(BaseModel):
    outline_text: str = Field(min_length=1)


class SectionInputsUpdate(BaseModel):
    user_inputs: dict[str, str]


class SectionManualEdit(BaseModel):
    draft_latex: str


class SectionVersionRead(BaseModel):
    id: str
    draft_latex: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SourceSuggestRequest(BaseModel):
    section_id: str | None = None
    query: str = Field(min_length=3, max_length=500)


class SourceCandidate(BaseModel):
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    abstract: str | None = None
    source: str
    source_paper_id: str | None = None
    source_url: str | None = None
    pdf_url: str | None = None
    pdf_available: bool = False
    arxiv_id: str | None = None


class SourceSuggestResponse(BaseModel):
    candidates: list[SourceCandidate]
    warnings: list[str] = Field(default_factory=list)


class SourceAttachRequest(BaseModel):
    candidate: SourceCandidate


class SourceAttachResponse(BaseModel):
    paper_id: str | None
    requires_upload: bool
    message: str


class AttachPaperIdRequest(BaseModel):
    paper_id: str


class ProjectSourceImportRequest(BaseModel):
    project_id: str
    paper_ids: list[str] = Field(min_length=1, max_length=100)


class ProjectSourceImportResponse(BaseModel):
    paper_ids: list[str]
    imported_count: int


class AssembleResponse(BaseModel):
    tex: str
    bib: str
    unresolved_todo_count: int
    warnings: list[str] = Field(default_factory=list)


class QAReport(BaseModel):
    unresolved_todos: list[dict[str, Any]]
    total_count: int


class WriterSectionDraftResponse(BaseModel):
    section: WriterSectionRead
    warnings: list[str] = Field(default_factory=list)


class TextSpanSchema(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_order(self) -> TextSpanSchema:
        if self.end < self.start:
            raise ValueError("span.end must be greater than or equal to span.start.")
        return self


class NewResultSchema(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    source_ref: str | None = Field(default=None, max_length=500)
    attach_as_citation: bool = False
    image_data: str | None = Field(default=None, max_length=5_000_000)


class EditRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=4000)
    span: TextSpanSchema | None = None
    insertion_offset: int | None = Field(default=None, ge=0)
    new_results: list[NewResultSchema] = Field(default_factory=list, max_length=20)
    web_search: bool = False
    web_query: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_target(self) -> EditRequest:
        if self.span is None and self.insertion_offset is None:
            raise ValueError("Either span or insertion_offset is required.")
        return self


class WebCitationSchema(BaseModel):
    title: str
    url: str
    snippet: str


class EditPatchResponse(BaseModel):
    span: TextSpanSchema
    new_text: str
    rationale: str
    web_citations: list[WebCitationSchema] = Field(default_factory=list)
    original_text: str = ""


class ChatSectionPatchSchema(BaseModel):
    section_id: str
    section_title: str
    span: TextSpanSchema
    original_text: str
    new_text: str
    rationale: str
    status: Literal["pending", "applied", "rejected", "stale"] = "pending"


class ChatMessageSchema(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    patches: list[ChatSectionPatchSchema] = Field(default_factory=list)
    created_at: datetime


class ChatRead(BaseModel):
    id: str
    document_id: str
    messages: list[ChatMessageSchema] = Field(default_factory=list)
    last_active_at: datetime
    history_summary: str = ""


class ChatMeta(BaseModel):
    id: str
    document_id: str
    last_active_at: datetime
    message_count: int


class ChatTurnRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4_000)


class ChatTurnRead(BaseModel):
    chat_id: str
    user_message: ChatMessageSchema
    assistant_message: ChatMessageSchema
