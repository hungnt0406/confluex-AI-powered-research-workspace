from datetime import date, datetime
from math import ceil
from typing import TYPE_CHECKING, Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

if TYPE_CHECKING:
    from backend.db.models import (
        DeepSearchRun,
        DeepSearchSource,
        PaperConversation,
        ProjectConversation,
        ReferenceFile,
        WriterOutput,
    )


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


class ProjectTitleUpdate(BaseModel):
    """Request body for renaming a project."""

    title: str = Field(min_length=1, max_length=255)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("title must not be empty.")
        return normalized


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


class TokenUsageBreakdownRow(BaseModel):
    """Aggregated token usage for a feature or model."""

    key: str
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    cost_credits: float | None
    request_count: int


class TokenUsageDailyRow(BaseModel):
    """Aggregated token usage for one calendar day."""

    day: date
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    cost_credits: float | None
    request_count: int


class ProjectTokenUsageRead(BaseModel):
    """Project-scoped provider-reported AI token usage summary."""

    project_id: str
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    cached_tokens: int
    cost_credits: float | None
    request_count: int
    by_feature: list[TokenUsageBreakdownRow]
    by_model: list[TokenUsageBreakdownRow]
    by_day: list[TokenUsageDailyRow]


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
    citation_count: int | None = None
    reference_count: int | None = None
    status: str
    relevance_score: float | None
    summary: PaperSummaryRead | None

    model_config = ConfigDict(from_attributes=True)


class CitationGraphPaperRead(BaseModel):
    """Serialized related-paper payload returned from citation graph lookups."""

    title: str
    authors: list[str]
    year: int | None
    abstract: str | None
    doi: str | None
    source: str
    source_paper_id: str | None
    source_url: str | None
    pdf_url: str | None
    citation_count: int | None = None


class CitationGraphPaperImport(BaseModel):
    """Request body for importing a citation-graph paper into a project."""

    title: str = Field(min_length=1, max_length=500)
    authors: list[str] = Field(default_factory=list)
    year: int | None = Field(default=None, ge=1000, le=2100)
    abstract: str | None = None
    doi: str | None = Field(default=None, max_length=255)
    source: str = Field(min_length=1, max_length=100)
    source_paper_id: str | None = Field(default=None, max_length=255)
    source_url: str | None = None
    pdf_url: str | None = None
    citation_count: int | None = Field(default=None, ge=0)

    @field_validator("title", "source")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty.")
        return normalized

    @field_validator("doi", "source_paper_id", "source_url", "pdf_url")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class CitationGraphPaperImportResponse(BaseModel):
    """Response returned after importing or matching a citation-graph paper."""

    paper: ProjectPaperRead
    created: bool


class PaperCitationGraphRead(BaseModel):
    """Citation and reference lists for one project paper."""

    paper_id: str
    resolved_by: str
    resolved_source_paper_id: str
    citation_count: int | None
    reference_count: int | None
    cited_by: list[CitationGraphPaperRead]
    references: list[CitationGraphPaperRead]


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


class ProjectConversationQuestionCreate(BaseModel):
    """Request body for project-scoped multi-paper chat questions."""

    paper_ids: list[str] = Field(max_length=5)
    question: str = Field(min_length=1, max_length=8_000)

    @model_validator(mode="after")
    def validate_paper_ids(self) -> "ProjectConversationQuestionCreate":
        normalized_ids = [paper_id.strip() for paper_id in self.paper_ids]
        if any(not paper_id for paper_id in normalized_ids):
            raise ValueError("paper_ids must not contain empty values.")
        if len(dict.fromkeys(normalized_ids)) != len(normalized_ids):
            raise ValueError("paper_ids must be unique.")
        self.paper_ids = normalized_ids
        self.question = self.question.strip()
        return self


class ProjectConversationCreate(ProjectConversationQuestionCreate):
    """Request body for starting a project-scoped multi-paper conversation."""


class ProjectConversationMessageCreate(ProjectConversationQuestionCreate):
    """Request body for adding a follow-up turn to a project-scoped conversation."""


class DeepSearchCreate(BaseModel):
    """Request body for starting a project-scoped deep search run."""

    paper_ids: list[str] = Field(max_length=5)
    question: str = Field(min_length=1, max_length=8_000)

    @model_validator(mode="after")
    def validate_payload(self) -> "DeepSearchCreate":
        normalized_ids = [paper_id.strip() for paper_id in self.paper_ids]
        if any(not paper_id for paper_id in normalized_ids):
            raise ValueError("paper_ids must not contain empty values.")
        if len(dict.fromkeys(normalized_ids)) != len(normalized_ids):
            raise ValueError("paper_ids must be unique.")
        self.paper_ids = normalized_ids
        self.question = self.question.strip()
        return self


class DeepSearchSourceRead(BaseModel):
    """Serialized source row collected for a deep search run."""

    id: str
    run_id: str
    source_type: Literal["paper", "paper_chunk", "citation_graph", "web"]
    title: str
    url: str | None
    paper_id: str | None
    snippet: str
    note: str
    metadata: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_source(cls, source: "DeepSearchSource") -> "DeepSearchSourceRead":
        metadata = dict(source.metadata_json)
        return cls(
            id=source.id,
            run_id=source.run_id,
            source_type=cast(
                Literal["paper", "paper_chunk", "citation_graph", "web"],
                source.source_type,
            ),
            title=source.title,
            url=source.url,
            paper_id=source.paper_id,
            snippet=source.snippet,
            note=str(metadata.get("note") or "").strip(),
            metadata=metadata,
            created_at=source.created_at,
        )


class DeepSearchRunSummaryRead(BaseModel):
    """Serialized deep search run summary for list views and run SSE events."""

    id: str
    project_id: str
    user_prompt: str
    status: Literal["running", "completed", "failed"]
    selected_paper_ids: list[str]
    source_count: int
    warning_count: int
    qa_flag_count: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    @classmethod
    def from_run(cls, run: "DeepSearchRun") -> "DeepSearchRunSummaryRead":
        loaded_sources = list(run.__dict__.get("sources", []))
        return cls(
            id=run.id,
            project_id=run.project_id,
            user_prompt=run.user_prompt,
            status=cast(Literal["running", "completed", "failed"], run.status),
            selected_paper_ids=list(run.selected_paper_ids_json),
            source_count=len(loaded_sources),
            warning_count=len(run.warnings_json),
            qa_flag_count=len(run.qa_flags_json),
            created_at=run.created_at,
            updated_at=run.updated_at,
            completed_at=run.completed_at,
        )


class DeepSearchRunRead(DeepSearchRunSummaryRead):
    """Serialized full deep search run with report and sources."""

    plan: dict[str, Any]
    report_body: str
    source_summary: dict[str, Any]
    warnings: list[str]
    qa_flags: list[dict[str, Any]]
    sources: list[DeepSearchSourceRead]

    @classmethod
    def from_run(cls, run: "DeepSearchRun") -> "DeepSearchRunRead":
        loaded_sources = list(run.__dict__.get("sources", []))
        return cls(
            id=run.id,
            project_id=run.project_id,
            user_prompt=run.user_prompt,
            status=cast(Literal["running", "completed", "failed"], run.status),
            selected_paper_ids=list(run.selected_paper_ids_json),
            source_count=len(loaded_sources),
            warning_count=len(run.warnings_json),
            qa_flag_count=len(run.qa_flags_json),
            created_at=run.created_at,
            updated_at=run.updated_at,
            completed_at=run.completed_at,
            plan=dict(run.plan_json),
            report_body=run.report_body,
            source_summary=dict(run.source_summary_json),
            warnings=list(run.warnings_json),
            qa_flags=[dict(flag) for flag in run.qa_flags_json],
            sources=[DeepSearchSourceRead.from_source(source) for source in loaded_sources],
        )


class ProjectMessageRead(BaseModel):
    """Serialized message payload for a project-scoped conversation."""

    id: str
    conversation_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectConversationRead(BaseModel):
    """Serialized project conversation with its persisted messages."""

    id: str
    project_id: str
    selected_paper_ids: list[str]
    created_at: datetime
    updated_at: datetime
    messages: list[ProjectMessageRead]

    @classmethod
    def from_conversation(cls, conversation: "ProjectConversation") -> "ProjectConversationRead":
        return cls(
            id=conversation.id,
            project_id=conversation.project_id,
            selected_paper_ids=list(conversation.selected_paper_ids_json),
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            messages=[
                ProjectMessageRead.model_validate(message)
                for message in conversation.messages
            ],
        )


class ProjectConversationSummaryRead(BaseModel):
    """Serialized summary payload for project-scoped conversations."""

    id: str
    project_id: str
    selected_paper_ids: list[str]
    created_at: datetime
    updated_at: datetime
    message_count: int
    opening_question: str | None

    @classmethod
    def from_conversation(
        cls,
        conversation: "ProjectConversation",
    ) -> "ProjectConversationSummaryRead":
        opening_question = next(
            (message.content for message in conversation.messages if message.role == "user"),
            None,
        )
        return cls(
            id=conversation.id,
            project_id=conversation.project_id,
            selected_paper_ids=list(conversation.selected_paper_ids_json),
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=len(conversation.messages),
            opening_question=opening_question,
        )


class WriterGenerateRequest(BaseModel):
    """Request body for generating a grounded writer artifact from selected papers."""

    paper_ids: list[str] = Field(min_length=1, max_length=50)
    instruction: str = Field(min_length=1, max_length=8_000)
    output_target: Literal["latex", "docs", "markdown", "plain_text"] = "markdown"
    citation_mode: Literal[
        "numbered",
        "author_year",
        "latex_cite",
        "bibtex_only",
        "thebibliography",
    ] | None = None
    reference_style: Literal["ieee", "apa", "chicago", "bibtex"] | None = None
    include_references: bool = True
    max_words: int | None = Field(default=None, ge=25, le=10_000)

    @model_validator(mode="after")
    def validate_output_settings(self) -> "WriterGenerateRequest":
        unique_paper_ids = list(dict.fromkeys(self.paper_ids))
        if len(unique_paper_ids) != len(self.paper_ids):
            raise ValueError("paper_ids must be unique.")

        if self.citation_mode in {"latex_cite", "thebibliography"} and self.output_target != "latex":
            raise ValueError(
                "latex_cite and thebibliography citation modes require output_target='latex'."
            )

        return self


class WriterQaFlagRead(BaseModel):
    """Serialized QA issue emitted for generated writer output."""

    issue: str
    severity: Literal["warning", "error"]
    location: str


class WriterPaperSnapshotRead(BaseModel):
    """Serialized paper snapshot stored alongside a persisted writer output."""

    id: str
    title: str
    authors: list[str]
    year: int | None
    doi: str | None
    source: str
    source_url: str | None
    pdf_url: str | None


class WriterOutputRead(BaseModel):
    """Serialized persisted writer output."""

    id: str
    project_id: str
    selected_paper_ids: list[str]
    paper_snapshot: list[WriterPaperSnapshotRead]
    instruction: str
    output_target: str
    citation_mode: str
    reference_style: str
    include_references: bool
    max_words: int | None
    body: str
    references: list[str]
    bibtex_entries: list[str]
    thebibliography: str | None
    citations_used: list[str]
    warnings: list[str]
    qa_flags: list[WriterQaFlagRead]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_writer_output(cls, writer_output: "WriterOutput") -> "WriterOutputRead":
        return cls(
            id=writer_output.id,
            project_id=writer_output.project_id,
            selected_paper_ids=list(writer_output.selected_paper_ids_json),
            paper_snapshot=[
                WriterPaperSnapshotRead.model_validate(snapshot)
                for snapshot in writer_output.paper_snapshot_json
            ],
            instruction=writer_output.instruction,
            output_target=writer_output.output_target,
            citation_mode=writer_output.citation_mode,
            reference_style=writer_output.reference_style,
            include_references=writer_output.include_references,
            max_words=writer_output.max_words,
            body=writer_output.body,
            references=list(writer_output.references_json),
            bibtex_entries=list(writer_output.bibtex_entries_json),
            thebibliography=writer_output.thebibliography_text,
            citations_used=list(writer_output.citations_used_json),
            warnings=list(writer_output.warnings_json),
            qa_flags=[
                WriterQaFlagRead.model_validate(flag_payload)
                for flag_payload in writer_output.qa_flags_json
            ],
            created_at=writer_output.created_at,
            updated_at=writer_output.updated_at,
        )


class PipelineHealthResponse(BaseModel):
    """Health payload for the dummy pipeline graph."""

    status: Literal["ok"]
    nodes: list[str]
