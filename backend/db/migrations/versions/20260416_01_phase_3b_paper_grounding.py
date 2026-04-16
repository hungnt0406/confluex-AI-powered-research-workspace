"""Add paper grounding documents and chunks."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260416_01"
down_revision: str | None = "20260415_01"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "paper_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("paper_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("source_pdf_url", sa.Text(), nullable=False),
        sa.Column("openrouter_file_hash", sa.String(length=255), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("paper_id"),
    )
    op.create_index(op.f("ix_paper_documents_paper_id"), "paper_documents", ["paper_id"], unique=True)

    op.create_table(
        "paper_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("paper_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("section_title", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("paper_id", "chunk_index", name="uq_paper_chunks_paper_chunk_index"),
    )
    op.create_index(op.f("ix_paper_chunks_paper_id"), "paper_chunks", ["paper_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_paper_chunks_paper_id"), table_name="paper_chunks")
    op.drop_table("paper_chunks")

    op.drop_index(op.f("ix_paper_documents_paper_id"), table_name="paper_documents")
    op.drop_table("paper_documents")
