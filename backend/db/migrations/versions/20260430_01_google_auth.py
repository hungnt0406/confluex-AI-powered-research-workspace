"""Add Google OAuth support to users table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260430_01"
down_revision: str | None = "20260426_01"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "auth_provider",
            sa.String(length=32),
            server_default="email",
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column("google_sub", sa.String(length=255), nullable=True),
    )
    op.create_index(op.f("ix_users_google_sub"), "users", ["google_sub"], unique=True)

    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.String(length=255),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.String(length=255),
        nullable=False,
    )

    op.drop_index(op.f("ix_users_google_sub"), table_name="users")
    op.drop_column("users", "google_sub")
    op.drop_column("users", "auth_provider")
