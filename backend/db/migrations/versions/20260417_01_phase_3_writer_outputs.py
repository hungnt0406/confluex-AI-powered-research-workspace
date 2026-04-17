"""Add persisted writer outputs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260417_01"
down_revision: str | None = "20260416_02"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "writer_outputs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("selected_paper_ids_json", sa.JSON(), nullable=False),
        sa.Column("paper_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("output_target", sa.String(length=32), nullable=False),
        sa.Column("citation_mode", sa.String(length=32), nullable=False),
        sa.Column("reference_style", sa.String(length=32), nullable=False),
        sa.Column("include_references", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("max_words", sa.Integer(), nullable=True),
        sa.Column("body", sa.Text(), server_default="", nullable=False),
        sa.Column("references_json", sa.JSON(), nullable=False),
        sa.Column("bibtex_entries_json", sa.JSON(), nullable=False),
        sa.Column("thebibliography_text", sa.Text(), nullable=True),
        sa.Column("citations_used_json", sa.JSON(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("qa_flags_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_writer_outputs_project_id"), "writer_outputs", ["project_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_writer_outputs_project_id"), table_name="writer_outputs")
    op.drop_table("writer_outputs")
