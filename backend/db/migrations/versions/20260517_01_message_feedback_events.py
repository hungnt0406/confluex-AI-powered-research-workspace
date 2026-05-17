"""Add message feedback telemetry table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260517_01"
down_revision: str | None = "20260513_01"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "message_feedback_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("message_id", sa.String(length=64), nullable=True),
        sa.Column("surface", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("content_preview", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_message_feedback_events_user_id"),
        "message_feedback_events",
        ["user_id"],
    )
    op.create_index(
        op.f("ix_message_feedback_events_project_id"),
        "message_feedback_events",
        ["project_id"],
    )
    op.create_index(
        op.f("ix_message_feedback_events_message_id"),
        "message_feedback_events",
        ["message_id"],
    )
    op.create_index(
        "ix_message_feedback_events_user_created_at",
        "message_feedback_events",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_message_feedback_events_surface_action",
        "message_feedback_events",
        ["surface", "action"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_message_feedback_events_surface_action",
        table_name="message_feedback_events",
    )
    op.drop_index(
        "ix_message_feedback_events_user_created_at",
        table_name="message_feedback_events",
    )
    op.drop_index(
        op.f("ix_message_feedback_events_message_id"),
        table_name="message_feedback_events",
    )
    op.drop_index(
        op.f("ix_message_feedback_events_project_id"),
        table_name="message_feedback_events",
    )
    op.drop_index(
        op.f("ix_message_feedback_events_user_id"),
        table_name="message_feedback_events",
    )
    op.drop_table("message_feedback_events")
