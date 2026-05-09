"""Add mode column to deep_search_runs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260509_01"
down_revision: str | None = "20260507_01"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "deep_search_runs",
        sa.Column(
            "mode",
            sa.String(length=32),
            server_default="standard",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("deep_search_runs", "mode")
