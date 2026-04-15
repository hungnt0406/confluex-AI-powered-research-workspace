"""Add project reference file uploads."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260415_01"
down_revision: str | None = "20260414_01"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reference_files",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("original_filename", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("parse_status", sa.String(length=32), server_default="parsed", nullable=False),
        sa.Column("extracted_title", sa.String(length=500), nullable=True),
        sa.Column("extracted_authors", sa.JSON(), nullable=False),
        sa.Column("extracted_year", sa.Integer(), nullable=True),
        sa.Column("extracted_abstract", sa.Text(), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "sha256", name="uq_reference_files_project_sha256"),
    )
    op.create_index(op.f("ix_reference_files_project_id"), "reference_files", ["project_id"])
    op.create_index(op.f("ix_reference_files_sha256"), "reference_files", ["sha256"])

    op.add_column(
        "papers",
        sa.Column("reference_file_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        op.f("ix_papers_reference_file_id"),
        "papers",
        ["reference_file_id"],
        unique=True,
    )
    op.create_foreign_key(
        "fk_papers_reference_file_id_reference_files",
        "papers",
        "reference_files",
        ["reference_file_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_papers_reference_file_id_reference_files", "papers", type_="foreignkey")
    op.drop_index(op.f("ix_papers_reference_file_id"), table_name="papers")
    op.drop_column("papers", "reference_file_id")

    op.drop_index(op.f("ix_reference_files_sha256"), table_name="reference_files")
    op.drop_index(op.f("ix_reference_files_project_id"), table_name="reference_files")
    op.drop_table("reference_files")
