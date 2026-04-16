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
    hashed_password: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    projects: Mapped[list[Project]] = relationship(back_populates="user", cascade="all, delete-orphan")


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
    reference_files: Mapped[list[ReferenceFile]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )


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
