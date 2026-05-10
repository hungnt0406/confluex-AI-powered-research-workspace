from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base


def generate_identifier() -> str:
    """Generate application-level identifiers."""

    return str(uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_identifier)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    auth_provider: Mapped[str] = mapped_column(
        String(32), default="email", server_default="email"
    )
    google_sub: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )
    credit_balance: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    country_code: Mapped[str] = mapped_column(String(8), default="VN", server_default="VN")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    projects: Mapped[list[Project]] = relationship(back_populates="user", cascade="all, delete-orphan")
    credit_transactions: Mapped[list[CreditTransaction]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="CreditTransaction.created_at.desc()",
    )
    payment_orders: Mapped[list[PaymentOrder]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="PaymentOrder.created_at.desc()",
    )


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"
    __table_args__ = (
        Index("ix_credit_transactions_user_created_at", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_identifier)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    delta: Mapped[int] = mapped_column(Integer)
    balance_after: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))
    feature: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="credit_transactions")


class PaymentOrder(Base):
    __tablename__ = "payment_orders"
    __table_args__ = (
        Index("ix_payment_orders_user_created_at", "user_id", "created_at"),
        Index("ix_payment_orders_status_expires_at", "status", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_identifier)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    pack_id: Mapped[str] = mapped_column(String(32))
    credits: Mapped[int] = mapped_column(Integer)
    usd_amount: Mapped[int] = mapped_column(Integer)
    vnd_amount: Mapped[int] = mapped_column(Integer)
    fx_rate_usd_to_vnd: Mapped[float] = mapped_column(Float)
    reference_code: Mapped[str] = mapped_column(String(32), unique=True)
    sepay_va_account: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sepay_va_bank_bin: Mapped[str | None] = mapped_column(String(16), nullable=True)
    qr_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    sepay_transaction_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[User] = relationship(back_populates="payment_orders")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_identifier)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    topic_description: Mapped[str] = mapped_column(Text)
    citation_format: Mapped[str] = mapped_column(String(100))
    year_start: Mapped[int] = mapped_column(Integer, default=2018, server_default="2018")
    candidate_limit: Mapped[int] = mapped_column(Integer, default=60, server_default="60")
    summary_limit: Mapped[int] = mapped_column(Integer, default=30, server_default="30")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="projects")
    papers: Mapped[list[Paper]] = relationship(back_populates="project", cascade="all, delete-orphan")
    drafts: Mapped[list[Draft]] = relationship(back_populates="project", cascade="all, delete-orphan")
    writer_outputs: Mapped[list[WriterOutput]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    conversations: Mapped[list[ProjectConversation]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectConversation.updated_at.desc()",
    )
    reference_files: Mapped[list[ReferenceFile]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    ai_usage_events: Mapped[list[AIUsageEvent]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    deep_search_runs: Mapped[list[DeepSearchRun]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="DeepSearchRun.created_at.desc()",
    )
    writer_documents: Mapped[list[WriterDocument]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="WriterDocument.created_at.desc()",
    )


class AIUsageEvent(Base):
    __tablename__ = "ai_usage_events"
    __table_args__ = (
        Index("ix_ai_usage_events_project_created_at", "project_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_identifier)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    endpoint: Mapped[str] = mapped_column(String(128))
    feature: Mapped[str] = mapped_column(String(128))
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="success", server_default="success")
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_credits: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship()
    project: Mapped[Project] = relationship(back_populates="ai_usage_events")


class ReferenceFile(Base):
    __tablename__ = "reference_files"
    __table_args__ = (
        UniqueConstraint("project_id", "sha256", name="uq_reference_files_project_sha256"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_identifier)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    original_filename: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    byte_size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_path: Mapped[str] = mapped_column(Text)
    parse_status: Mapped[str] = mapped_column(String(32), default="parsed", server_default="parsed")
    extracted_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    extracted_authors: Mapped[list[str]] = mapped_column(JSON, default=list)
    extracted_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extracted_abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    project: Mapped[Project] = relationship(back_populates="reference_files")
    paper: Mapped[Paper | None] = relationship(
        back_populates="reference_file",
        uselist=False,
    )


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_identifier)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(500))
    authors: Mapped[list[str]] = mapped_column(JSON, default=list)
    year: Mapped[int | None] = mapped_column(nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(100))
    reference_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("reference_files.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=True,
    )
    source_paper_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    citation_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reference_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="candidate", server_default="candidate")
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    project: Mapped[Project] = relationship(back_populates="papers")
    reference_file: Mapped[ReferenceFile | None] = relationship(back_populates="paper")
    document: Mapped[PaperDocument | None] = relationship(
        back_populates="paper",
        cascade="all, delete-orphan",
        uselist=False,
    )
    chunks: Mapped[list[PaperChunk]] = relationship(
        back_populates="paper",
        cascade="all, delete-orphan",
        order_by="PaperChunk.chunk_index",
    )
    conversations: Mapped[list[PaperConversation]] = relationship(
        back_populates="paper",
        cascade="all, delete-orphan",
        order_by="PaperConversation.updated_at.desc()",
    )
    summary: Mapped[Summary | None] = relationship(
        back_populates="paper",
        cascade="all, delete-orphan",
        uselist=False,
    )
    deep_search_sources: Mapped[list[DeepSearchSource]] = relationship(
        back_populates="paper",
    )


class PaperDocument(Base):
    __tablename__ = "paper_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_identifier)
    paper_id: Mapped[str] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), default="pending", server_default="pending")
    source_pdf_url: Mapped[str] = mapped_column(Text)
    openrouter_file_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    paper: Mapped[Paper] = relationship(back_populates="document")


class PaperChunk(Base):
    __tablename__ = "paper_chunks"
    __table_args__ = (
        UniqueConstraint("paper_id", "chunk_index", name="uq_paper_chunks_paper_chunk_index"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_identifier)
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    page_start: Mapped[int] = mapped_column(Integer)
    page_end: Mapped[int] = mapped_column(Integer)
    section_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    embedding_json: Mapped[list[float]] = mapped_column(JSON, default=list)

    paper: Mapped[Paper] = relationship(back_populates="chunks")


class PaperConversation(Base):
    __tablename__ = "paper_conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_identifier)
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    paper: Mapped[Paper] = relationship(back_populates="conversations")
    messages: Mapped[list[PaperMessage]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="PaperMessage.created_at.asc()",
    )


class PaperMessage(Base):
    __tablename__ = "paper_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_identifier)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("paper_conversations.id", ondelete="CASCADE"),
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    conversation: Mapped[PaperConversation] = relationship(back_populates="messages")


class ProjectConversation(Base):
    __tablename__ = "project_conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_identifier)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    selected_paper_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    project: Mapped[Project] = relationship(back_populates="conversations")
    messages: Mapped[list[ProjectMessage]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ProjectMessage.created_at.asc()",
    )


class ProjectMessage(Base):
    __tablename__ = "project_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_identifier)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("project_conversations.id", ondelete="CASCADE"),
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    conversation: Mapped[ProjectConversation] = relationship(back_populates="messages")


class DeepSearchRun(Base):
    __tablename__ = "deep_search_runs"
    __table_args__ = (
        Index("ix_deep_search_runs_project_created_at", "project_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_identifier)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    user_prompt: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="running", server_default="running")
    mode: Mapped[str] = mapped_column(String(32), default="standard", server_default="standard")
    selected_paper_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    plan_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    report_body: Mapped[str] = mapped_column(Text, default="", server_default="")
    source_summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    warnings_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    qa_flags_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="deep_search_runs")
    sources: Mapped[list[DeepSearchSource]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="DeepSearchSource.created_at.asc()",
    )


class DeepSearchSource(Base):
    __tablename__ = "deep_search_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_identifier)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("deep_search_runs.id", ondelete="CASCADE"),
        index=True,
    )
    source_type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    paper_id: Mapped[str | None] = mapped_column(
        ForeignKey("papers.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    snippet: Mapped[str] = mapped_column(Text, default="", server_default="")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    run: Mapped[DeepSearchRun] = relationship(back_populates="sources")
    paper: Mapped[Paper | None] = relationship(back_populates="deep_search_sources")


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_identifier)
    paper_id: Mapped[str] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    problem: Mapped[str | None] = mapped_column(Text, nullable=True)
    method: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    relevance_to_topic: Mapped[str | None] = mapped_column(Text, nullable=True)
    has_error: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    paper: Mapped[Paper] = relationship(back_populates="summary")


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_identifier)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    outline_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    word_count: Mapped[int] = mapped_column(default=0)
    qa_flags_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="drafts")


class WriterDocument(Base):
    __tablename__ = "writer_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_identifier)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(500), default="Untitled Paper")
    topic: Mapped[str] = mapped_column(Text)
    thesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    paper_type: Mapped[str] = mapped_column(String(32), default="imrad", server_default="imrad")
    citation_style: Mapped[str] = mapped_column(String(32), default="ieee", server_default="ieee")
    preamble: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_paper_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    bib_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="outline", server_default="outline")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    project: Mapped[Project] = relationship(back_populates="writer_documents")
    sections: Mapped[list[WriterSection]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="WriterSection.order_index",
    )


class WriterSection(Base):
    __tablename__ = "writer_sections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_identifier)
    writer_document_id: Mapped[str] = mapped_column(
        ForeignKey("writer_documents.id", ondelete="CASCADE"), index=True
    )
    section_type: Mapped[str] = mapped_column(String(64))
    order_index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(500))
    outline_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_inputs_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    draft_latex: Mapped[str | None] = mapped_column(Text, nullable=True)
    low_confidence_spans_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    cited_paper_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="planned", server_default="planned")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    document: Mapped[WriterDocument] = relationship(back_populates="sections")
    versions: Mapped[list[WriterSectionVersion]] = relationship(
        back_populates="section",
        cascade="all, delete-orphan",
        order_by="WriterSectionVersion.created_at.desc()",
    )


class WriterSectionVersion(Base):
    __tablename__ = "writer_section_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_identifier)
    writer_section_id: Mapped[str] = mapped_column(
        ForeignKey("writer_sections.id", ondelete="CASCADE"), index=True
    )
    draft_latex: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    section: Mapped[WriterSection] = relationship(back_populates="versions")


class WriterOutput(Base):
    __tablename__ = "writer_outputs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_identifier)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    selected_paper_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    paper_snapshot_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    instruction: Mapped[str] = mapped_column(Text)
    output_target: Mapped[str] = mapped_column(String(32))
    citation_mode: Mapped[str] = mapped_column(String(32))
    reference_style: Mapped[str] = mapped_column(String(32))
    include_references: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="1",
    )
    max_words: Mapped[int | None] = mapped_column(Integer, nullable=True)
    body: Mapped[str] = mapped_column(Text, default="", server_default="")
    references_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    bibtex_entries_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    thebibliography_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    citations_used_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    warnings_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    qa_flags_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    project: Mapped[Project] = relationship(back_populates="writer_outputs")
