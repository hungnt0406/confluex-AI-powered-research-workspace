"""Add phase 2 searcher and reader fields."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260411_02"
down_revision: str | None = "20260411_01"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("year_start", sa.Integer(), nullable=False, server_default="2018"),
    )
    op.add_column(
        "projects",
        sa.Column("candidate_limit", sa.Integer(), nullable=False, server_default="60"),
    )
    op.add_column(
        "projects",
        sa.Column("summary_limit", sa.Integer(), nullable=False, server_default="30"),
    )

    op.add_column(
        "papers",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="candidate"),
    )

    op.add_column(
        "summaries",
        sa.Column("has_error", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "summaries",
        sa.Column("error_message", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("summaries", "error_message")
    op.drop_column("summaries", "has_error")
    op.drop_column("papers", "status")
    op.drop_column("projects", "summary_limit")
    op.drop_column("projects", "candidate_limit")
    op.drop_column("projects", "year_start")
