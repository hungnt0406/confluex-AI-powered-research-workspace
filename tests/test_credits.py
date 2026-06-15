import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.db.models import CreditTransaction, User
from backend.security import hash_password
from backend.services.credits import InsufficientCreditsError, credit, debit, get_balance


async def create_user(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    email: str,
    credit_balance: int = 0,
) -> User:
    async with session_factory() as session:
        user = User(
            email=email,
            hashed_password=hash_password("supersecret123"),
            credit_balance=credit_balance,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.mark.asyncio
async def test_credit_and_debit_round_trip_persists_ledger_balances(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await create_user(session_factory, email="ledger@example.com")

    async with session_factory() as session:
        grant_tx = await credit(
            session,
            user_id=user.id,
            delta=100,
            kind="grant",
            metadata={"reason": "signup_bonus"},
        )
        await session.commit()

        consume_tx = await debit(
            session,
            user_id=user.id,
            amount=40,
            feature="writer",
            reference_id="writer-output-1",
            metadata={"source": "test"},
        )
        await session.commit()

        refund_tx = await credit(
            session,
            user_id=user.id,
            delta=15,
            kind="refund",
            feature="writer",
            reference_id="writer-output-1",
            metadata={"reason": "partial_refund"},
        )
        await session.commit()

        persisted_user = await session.get(User, user.id)
        transactions = list(
            (
                await session.execute(
                    select(CreditTransaction).where(CreditTransaction.user_id == user.id)
                )
            ).scalars()
        )

    async with session_factory() as session:
        balance = await get_balance(session, user.id)

    assert grant_tx.delta == 100
    assert grant_tx.balance_after == 100
    assert consume_tx.delta == -40
    assert consume_tx.balance_after == 60
    assert refund_tx.delta == 15
    assert refund_tx.balance_after == 75
    assert persisted_user is not None
    assert persisted_user.credit_balance == 75
    assert len(transactions) == 3
    assert balance == 75


@pytest.mark.asyncio
async def test_debit_raises_insufficient_credits_without_inserting_transaction(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await create_user(session_factory, email="empty-balance@example.com")

    async with session_factory() as session:
        with pytest.raises(InsufficientCreditsError) as error_info:
            await debit(session, user_id=user.id, amount=5, feature="deep_search")
        await session.rollback()

        transactions = list(
            (
                await session.execute(
                    select(CreditTransaction).where(CreditTransaction.user_id == user.id)
                )
            ).scalars()
        )
        persisted_user = await session.get(User, user.id)

    assert error_info.value.required == 5
    assert error_info.value.balance == 0
    assert transactions == []
    assert persisted_user is not None
    assert persisted_user.credit_balance == 0


@pytest.mark.asyncio
async def test_register_grants_signup_bonus_and_ledgers_it(client, session_factory) -> None:
    response = await client.post(
        "/auth/register",
        json={
            "email": "signup-bonus@example.com",
            "password": "strongpass123",
            "agreed_to_terms": True,
        },
    )

    assert response.status_code == 201
    payload = response.json()

    async with session_factory() as session:
        user = await session.get(User, payload["user"]["id"])
        transactions = list(
            (
                await session.execute(
                    select(CreditTransaction)
                    .where(CreditTransaction.user_id == payload["user"]["id"])
                    .order_by(CreditTransaction.created_at.asc(), CreditTransaction.id.asc())
                )
            ).scalars()
        )

    assert user is not None
    assert user.credit_balance == 1600
    assert len(transactions) == 1
    assert transactions[0].kind == "grant"
    assert transactions[0].delta == 1600
    assert transactions[0].balance_after == 1600
    assert transactions[0].metadata_json == {"reason": "signup_bonus"}
