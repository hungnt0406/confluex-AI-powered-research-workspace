"""Add citation and reference counts to papers."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260420_01"
down_revision: str | None = "20260417_01"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("papers", sa.Column("citation_count", sa.Integer(), nullable=True))
    op.add_column("papers", sa.Column("reference_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("papers", "reference_count")
    op.drop_column("papers", "citation_count")
