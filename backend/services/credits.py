from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import CreditTransaction, User


class InsufficientCreditsError(RuntimeError):
    """Raised when a debit would take a user's balance below zero."""

    def __init__(self, *, required: int, balance: int):
        super().__init__("Insufficient credits.")
        self.required = required
        self.balance = balance


async def _get_locked_user(session: AsyncSession, user_id: str) -> User:
    statement = select(User).where(User.id == user_id)
    if session.get_bind().dialect.name != "sqlite":
        statement = statement.with_for_update()

    result = await session.execute(statement)
    user = result.scalar_one_or_none()
    if user is None:
        raise LookupError("User not found.")
    return user


async def credit(
    session: AsyncSession,
    user_id: str,
    delta: int,
    kind: str,
    *,
    feature: str | None = None,
    reference_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> CreditTransaction:
    """Increase a user's balance and persist the audit ledger row."""

    if delta <= 0:
        raise ValueError("delta must be positive.")

    user = await _get_locked_user(session, user_id)
    user.credit_balance += delta
    transaction = CreditTransaction(
        user_id=user.id,
        delta=delta,
        balance_after=user.credit_balance,
        kind=kind,
        feature=feature,
        reference_id=reference_id,
        metadata_json=dict(metadata or {}),
    )
    session.add(transaction)
    await session.flush()
    return transaction


async def debit(
    session: AsyncSession,
    user_id: str,
    amount: int,
    feature: str,
    *,
    reference_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> CreditTransaction:
    """Decrease a user's balance and persist the audit ledger row."""

    if amount <= 0:
        raise ValueError("amount must be positive.")

    user = await _get_locked_user(session, user_id)
    if user.credit_balance < amount:
        raise InsufficientCreditsError(required=amount, balance=user.credit_balance)

    user.credit_balance -= amount
    transaction = CreditTransaction(
        user_id=user.id,
        delta=-amount,
        balance_after=user.credit_balance,
        kind="consume",
        feature=feature,
        reference_id=reference_id,
        metadata_json=dict(metadata or {}),
    )
    session.add(transaction)
    await session.flush()
    return transaction


async def get_balance(session: AsyncSession, user_id: str) -> int:
    """Return the current user balance."""

    result = await session.execute(select(User.credit_balance).where(User.id == user_id))
    balance = result.scalar_one_or_none()
    if balance is None:
        raise LookupError("User not found.")
    return int(balance)
