from __future__ import annotations

import secrets
import string
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import CreditPack, get_settings
from backend.db.models import PaymentOrder, User
from backend.services.credits import credit
from backend.services.fx import usd_cents_to_vnd
from backend.services.sepay import build_vietqr_payload

REFERENCE_CODE_ALPHABET = string.ascii_uppercase + string.digits
REFERENCE_CODE_LENGTH = 8
ORDER_EXPIRY_MINUTES = 30


class UnknownCreditPackError(ValueError):
    """Raised when a requested credit pack is not in the catalog."""


def _now() -> datetime:
    return datetime.now(UTC)


def _is_expired(expires_at: datetime) -> bool:
    now = _now()
    if expires_at.tzinfo is None:
        return expires_at <= now.replace(tzinfo=None)
    return expires_at <= now


async def _generate_reference_code(session: AsyncSession) -> str:
    for _ in range(10):
        code = "ORD" + "".join(
            secrets.choice(REFERENCE_CODE_ALPHABET) for _ in range(REFERENCE_CODE_LENGTH)
        )
        result = await session.execute(
            select(PaymentOrder.id).where(PaymentOrder.reference_code == code)
        )
        if result.scalar_one_or_none() is None:
            return code
    raise RuntimeError("Could not generate a unique payment reference code.")


def _resolve_pack(pack_id: str) -> CreditPack:
    pack = get_settings().credit_pack_by_id.get(pack_id)
    if pack is None:
        raise UnknownCreditPackError(f"Unknown credit pack '{pack_id}'.")
    return pack


async def create_order(
    session: AsyncSession,
    *,
    user: User,
    pack_id: str,
) -> PaymentOrder:
    """Create and persist a pending payment order for a configured credit pack."""

    settings = get_settings()
    pack = _resolve_pack(pack_id)
    reference_code = await _generate_reference_code(session)
    vnd_amount = usd_cents_to_vnd(pack.usd_cents, settings.usd_to_vnd_rate)
    created_at = _now()
    expires_at = created_at + timedelta(minutes=ORDER_EXPIRY_MINUTES)
    qr_payload = build_vietqr_payload(
        settings.sepay_account_number,
        settings.sepay_account_bank_bin,
        vnd_amount,
        reference_code,
    )
    order = PaymentOrder(
        user_id=user.id,
        pack_id=pack.id,
        credits=pack.credits,
        usd_amount=pack.usd_cents,
        vnd_amount=vnd_amount,
        fx_rate_usd_to_vnd=settings.usd_to_vnd_rate,
        reference_code=reference_code,
        sepay_va_account=settings.sepay_account_number or None,
        sepay_va_bank_bin=settings.sepay_account_bank_bin or None,
        qr_payload=qr_payload,
        status="pending",
        expires_at=expires_at,
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order


async def mark_order_paid(
    session: AsyncSession,
    *,
    reference_code: str,
    sepay_transaction_id: str,
    paid_amount_vnd: int,
) -> PaymentOrder | None:
    """Mark an order paid exactly once and grant the purchased credits."""

    existing_result = await session.execute(
        select(PaymentOrder).where(PaymentOrder.sepay_transaction_id == sepay_transaction_id)
    )
    existing_order = existing_result.scalar_one_or_none()
    if existing_order is not None:
        return existing_order

    statement = select(PaymentOrder).where(PaymentOrder.reference_code == reference_code)
    if session.get_bind().dialect.name != "sqlite":
        statement = statement.with_for_update()

    result = await session.execute(statement)
    order = result.scalar_one_or_none()
    if order is None:
        return None
    if order.status == "paid":
        return order
    if order.status != "pending":
        return None
    if _is_expired(order.expires_at):
        order.status = "expired"
        await session.commit()
        return None
    if paid_amount_vnd < order.vnd_amount:
        return None

    order.status = "paid"
    order.sepay_transaction_id = sepay_transaction_id
    order.paid_at = _now()
    await credit(
        session,
        user_id=order.user_id,
        delta=order.credits,
        kind="topup",
        reference_id=order.id,
        metadata={
            "sepay_transaction_id": sepay_transaction_id,
            "paid_amount_vnd": paid_amount_vnd,
            "reference_code": order.reference_code,
        },
    )
    await session.commit()
    await session.refresh(order)
    return order


async def expire_stale_orders(session: AsyncSession) -> int:
    """Expire pending payment orders whose validity window has elapsed."""

    result = await session.execute(
        update(PaymentOrder)
        .where(
            PaymentOrder.status == "pending",
            PaymentOrder.expires_at < _now(),
        )
        .values(status="expired")
    )
    await session.commit()
    rowcount = getattr(result, "rowcount", None)
    return int(rowcount or 0)
