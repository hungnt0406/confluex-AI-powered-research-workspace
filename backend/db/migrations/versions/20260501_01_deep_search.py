"""Add persisted deep search runs and sources."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260501_01"
down_revision: str | None = "20260430_01"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "deep_search_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("user_prompt", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="running", nullable=False),
        sa.Column("selected_paper_ids_json", sa.JSON(), nullable=False),
        sa.Column("plan_json", sa.JSON(), nullable=False),
        sa.Column("report_body", sa.Text(), server_default="", nullable=False),
        sa.Column("source_summary_json", sa.JSON(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("qa_flags_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_deep_search_runs_project_id"), "deep_search_runs", ["project_id"])
    op.create_index(
        "ix_deep_search_runs_project_created_at",
        "deep_search_runs",
        ["project_id", "created_at"],
    )

    op.create_table(
        "deep_search_sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("paper_id", sa.String(length=36), nullable=True),
        sa.Column("snippet", sa.Text(), server_default="", nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["deep_search_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_deep_search_sources_paper_id"), "deep_search_sources", ["paper_id"])
    op.create_index(op.f("ix_deep_search_sources_run_id"), "deep_search_sources", ["run_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_deep_search_sources_run_id"), table_name="deep_search_sources")
    op.drop_index(op.f("ix_deep_search_sources_paper_id"), table_name="deep_search_sources")
    op.drop_table("deep_search_sources")
    op.drop_index("ix_deep_search_runs_project_created_at", table_name="deep_search_runs")
    op.drop_index(op.f("ix_deep_search_runs_project_id"), table_name="deep_search_runs")
    op.drop_table("deep_search_runs")
