"""Add paper conversation persistence."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260416_02"
down_revision: str | None = "20260416_01"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "paper_conversations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("paper_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_paper_conversations_paper_id"),
        "paper_conversations",
        ["paper_id"],
        unique=False,
    )

    op.create_table(
        "paper_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["paper_conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_paper_messages_conversation_id"),
        "paper_messages",
        ["conversation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_paper_messages_conversation_id"), table_name="paper_messages")
    op.drop_table("paper_messages")

    op.drop_index(op.f("ix_paper_conversations_paper_id"), table_name="paper_conversations")
    op.drop_table("paper_conversations")
