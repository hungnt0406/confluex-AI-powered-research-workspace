"""Add writer workspace tables (writer_documents, writer_sections, writer_section_versions)."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260509_02"
down_revision: str | None = "20260509_01"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "writer_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False, server_default="Untitled Paper"),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("thesis", sa.Text(), nullable=True),
        sa.Column("paper_type", sa.String(length=32), nullable=False, server_default="imrad"),
        sa.Column("citation_style", sa.String(length=32), nullable=False, server_default="ieee"),
        sa.Column("preamble", sa.Text(), nullable=True),
        sa.Column("source_paper_ids_json", sa.JSON(), nullable=False),
        sa.Column("bib_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="outline"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_writer_documents_project_id", "writer_documents", ["project_id"])

    op.create_table(
        "writer_sections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("writer_document_id", sa.String(length=36), nullable=False),
        sa.Column("section_type", sa.String(length=64), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("outline_text", sa.Text(), nullable=True),
        sa.Column("user_inputs_json", sa.JSON(), nullable=False),
        sa.Column("draft_latex", sa.Text(), nullable=True),
        sa.Column("low_confidence_spans_json", sa.JSON(), nullable=False),
        sa.Column("cited_paper_ids_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="planned"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["writer_document_id"], ["writer_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_writer_sections_writer_document_id", "writer_sections", ["writer_document_id"])

    op.create_table(
        "writer_section_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("writer_section_id", sa.String(length=36), nullable=False),
        sa.Column("draft_latex", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["writer_section_id"], ["writer_sections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_writer_section_versions_section_id", "writer_section_versions", ["writer_section_id"]
    )


def downgrade() -> None:
    op.drop_table("writer_section_versions")
    op.drop_table("writer_sections")
    op.drop_table("writer_documents")
