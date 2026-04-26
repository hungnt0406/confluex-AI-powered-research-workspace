"""Add project-scoped AI usage telemetry."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260426_01"
down_revision: str | None = "20260424_01"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_usage_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("endpoint", sa.String(length=128), nullable=False),
        sa.Column("feature", sa.String(length=128), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="success", nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_credits", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_usage_events_project_id"), "ai_usage_events", ["project_id"])
    op.create_index(op.f("ix_ai_usage_events_user_id"), "ai_usage_events", ["user_id"])
    op.create_index(
        "ix_ai_usage_events_project_created_at",
        "ai_usage_events",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_usage_events_project_created_at", table_name="ai_usage_events")
    op.drop_index(op.f("ix_ai_usage_events_user_id"), table_name="ai_usage_events")
    op.drop_index(op.f("ix_ai_usage_events_project_id"), table_name="ai_usage_events")
    op.drop_table("ai_usage_events")
