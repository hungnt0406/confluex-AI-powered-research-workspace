"""Pydantic schemas for the writer workspace endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


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


class WriterDocumentRead(BaseModel):
    id: str
    project_id: str
    title: str
    topic: str
    thesis: str | None
    paper_type: str
    citation_style: str
    preamble: str | None
    source_paper_ids_json: list[str]
    status: str
    created_at: datetime
    updated_at: datetime
    sections: list[WriterSectionRead]

    model_config = {"from_attributes": True}


class WriterDocumentSummaryRead(BaseModel):
    id: str
    project_id: str
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
