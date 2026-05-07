"""Add user credits ledger and Sepay payment orders."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260507_01"
down_revision: str | None = "20260501_01"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("credit_balance", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("country_code", sa.String(length=8), server_default="VN", nullable=False),
    )

    op.create_table(
        "credit_transactions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("feature", sa.String(length=64), nullable=True),
        sa.Column("reference_id", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_credit_transactions_user_id"), "credit_transactions", ["user_id"])
    op.create_index(
        "ix_credit_transactions_user_created_at",
        "credit_transactions",
        ["user_id", "created_at"],
    )

    op.create_table(
        "payment_orders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("pack_id", sa.String(length=32), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("usd_amount", sa.Integer(), nullable=False),
        sa.Column("vnd_amount", sa.Integer(), nullable=False),
        sa.Column("fx_rate_usd_to_vnd", sa.Float(), nullable=False),
        sa.Column("reference_code", sa.String(length=32), nullable=False),
        sa.Column("sepay_va_account", sa.String(length=64), nullable=True),
        sa.Column("sepay_va_bank_bin", sa.String(length=16), nullable=True),
        sa.Column("qr_payload", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("sepay_transaction_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference_code"),
        sa.UniqueConstraint("sepay_transaction_id"),
    )
    op.create_index(op.f("ix_payment_orders_user_id"), "payment_orders", ["user_id"])
    op.create_index(
        "ix_payment_orders_user_created_at",
        "payment_orders",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_payment_orders_status_expires_at",
        "payment_orders",
        ["status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_payment_orders_status_expires_at", table_name="payment_orders")
    op.drop_index("ix_payment_orders_user_created_at", table_name="payment_orders")
    op.drop_index(op.f("ix_payment_orders_user_id"), table_name="payment_orders")
    op.drop_table("payment_orders")
    op.drop_index("ix_credit_transactions_user_created_at", table_name="credit_transactions")
    op.drop_index(op.f("ix_credit_transactions_user_id"), table_name="credit_transactions")
    op.drop_table("credit_transactions")
    op.drop_column("users", "country_code")
    op.drop_column("users", "credit_balance")
