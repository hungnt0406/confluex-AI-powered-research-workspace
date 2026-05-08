from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.config import CreditPack
from backend.db.models import CreditTransaction, PaymentOrder


class CreditPackRead(BaseModel):
    """Serialized credit pack catalog row."""

    id: str
    name: str
    usd_cents: int
    credits: int
    badge: str | None
    vnd_amount: int

    @classmethod
    def from_pack(cls, pack: CreditPack, *, vnd_amount: int) -> "CreditPackRead":
        return cls(
            id=pack.id,
            name=pack.name,
            usd_cents=pack.usd_cents,
            credits=pack.credits,
            badge=pack.badge,
            vnd_amount=vnd_amount,
        )


class PaymentOrderCreate(BaseModel):
    """Request body for creating a payment order."""

    pack_id: str = Field(min_length=1, max_length=32)


class PaymentOrderRead(BaseModel):
    """Serialized payment order payload."""

    id: str
    pack_id: str
    credits: int
    usd_amount: int
    vnd_amount: int
    fx_rate_usd_to_vnd: float
    reference_code: str
    account_number: str | None
    bank_bin: str | None
    qr_url: str | None
    status: str
    created_at: datetime
    paid_at: datetime | None
    expires_at: datetime

    @classmethod
    def from_order(cls, order: PaymentOrder) -> "PaymentOrderRead":
        return cls(
            id=order.id,
            pack_id=order.pack_id,
            credits=order.credits,
            usd_amount=order.usd_amount,
            vnd_amount=order.vnd_amount,
            fx_rate_usd_to_vnd=order.fx_rate_usd_to_vnd,
            reference_code=order.reference_code,
            account_number=order.sepay_va_account,
            bank_bin=order.sepay_va_bank_bin,
            qr_url=order.qr_payload,
            status=order.status,
            created_at=order.created_at,
            paid_at=order.paid_at,
            expires_at=order.expires_at,
        )


class CreditTransactionRead(BaseModel):
    """Serialized credit ledger row."""

    id: str
    delta: int
    balance_after: int
    kind: str
    feature: str | None
    reference_id: str | None
    metadata: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_transaction(cls, transaction: CreditTransaction) -> "CreditTransactionRead":
        return cls(
            id=transaction.id,
            delta=transaction.delta,
            balance_after=transaction.balance_after,
            kind=transaction.kind,
            feature=transaction.feature,
            reference_id=transaction.reference_id,
            metadata=dict(transaction.metadata_json),
            created_at=transaction.created_at,
        )


class PaymentBalanceRead(BaseModel):
    """Current user balance plus recent ledger rows."""

    credit_balance: int
    is_unlimited: bool = False
    recent_transactions: list[CreditTransactionRead]


class SepayWebhookPayload(BaseModel):
    """Subset of the Sepay webhook payload used in phase 1."""

    transaction_id: str = Field(alias="id")
    transfer_type: str | None = Field(default=None, alias="transferType")
    content: str | None = None
    transfer_amount: int | None = Field(default=None, alias="transferAmount")
    account_number: str | None = Field(default=None, alias="accountNumber")

    model_config = ConfigDict(
        populate_by_name=True, extra="ignore", coerce_numbers_to_str=True
    )


class SepayWebhookResponse(BaseModel):
    """Outcome returned to Sepay for one webhook notification."""

    matched: bool
    status: str | None = None
    order_id: str | None = None
