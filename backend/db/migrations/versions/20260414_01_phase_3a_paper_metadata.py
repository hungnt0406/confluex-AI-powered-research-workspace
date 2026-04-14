"""Add provider metadata fields to papers."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260414_01"
down_revision: str | None = "20260411_02"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "papers",
        sa.Column("source_paper_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "papers",
        sa.Column("source_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "papers",
        sa.Column("pdf_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("papers", "pdf_url")
    op.drop_column("papers", "source_url")
    op.drop_column("papers", "source_paper_id")
