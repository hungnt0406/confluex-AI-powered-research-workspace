from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.api.dependencies import get_db_session
from backend.config import get_settings
from backend.db.models import CreditTransaction, User
from backend.main import create_app
from backend.security import create_access_token, hash_password
from backend.services.payment_orders import create_order, mark_order_paid


async def create_user(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    email: str,
) -> User:
    async with session_factory() as session:
        user = User(email=email, hashed_password=hash_password("supersecret123"))
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest_asyncio.fixture
async def payments_client(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncClient:
    monkeypatch.setenv("SEPAY_ACCOUNT_NUMBER", "0123456789")
    monkeypatch.setenv("SEPAY_ACCOUNT_BANK_BIN", "MB")
    monkeypatch.setenv("USD_TO_VND_RATE", "25000")
    get_settings.cache_clear()

    app = create_app()

    async def override_get_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_order_snapshots_rate_and_rounds_vnd_amount(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEPAY_ACCOUNT_NUMBER", "0123456789")
    monkeypatch.setenv("SEPAY_ACCOUNT_BANK_BIN", "MB")
    monkeypatch.setenv("USD_TO_VND_RATE", "25000")
    get_settings.cache_clear()
    user = await create_user(session_factory, email="orders@example.com")

    async with session_factory() as session:
        order = await create_order(session, user=user, pack_id="student")

    assert order.pack_id == "student"
    assert order.credits == 800
    assert order.usd_amount == 800
    assert order.vnd_amount == 200_000
    assert order.fx_rate_usd_to_vnd == 25_000
    assert order.status == "pending"
    assert order.reference_code.startswith("ORD")
    assert "acc=0123456789" in order.qr_payload
    assert "bank=MB" in order.qr_payload
    assert f"des={order.reference_code}" in order.qr_payload


@pytest.mark.asyncio
async def test_create_order_generates_unique_reference_codes(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEPAY_ACCOUNT_NUMBER", "0123456789")
    monkeypatch.setenv("SEPAY_ACCOUNT_BANK_BIN", "MB")
    get_settings.cache_clear()
    user = await create_user(session_factory, email="many-orders@example.com")

    async with session_factory() as session:
        reference_codes: set[str] = set()
        for _ in range(25):
            order = await create_order(session, user=user, pack_id="topup_deep")
            reference_codes.add(order.reference_code)

    assert len(reference_codes) == 25


@pytest.mark.asyncio
async def test_mark_order_paid_is_idempotent_and_credits_once(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEPAY_ACCOUNT_NUMBER", "0123456789")
    monkeypatch.setenv("SEPAY_ACCOUNT_BANK_BIN", "MB")
    monkeypatch.setenv("USD_TO_VND_RATE", "25000")
    get_settings.cache_clear()
    user = await create_user(session_factory, email="idempotent-order@example.com")

    async with session_factory() as session:
        order = await create_order(session, user=user, pack_id="pro")
        first = await mark_order_paid(
            session,
            reference_code=order.reference_code,
            sepay_transaction_id="sepay-txn-1",
            paid_amount_vnd=order.vnd_amount,
        )
        second = await mark_order_paid(
            session,
            reference_code=order.reference_code,
            sepay_transaction_id="sepay-txn-1",
            paid_amount_vnd=order.vnd_amount,
        )

        persisted_user = await session.get(User, user.id)
        transactions = list(
            (
                await session.execute(
                    select(CreditTransaction).where(CreditTransaction.user_id == user.id)
                )
            ).scalars()
        )

    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert first.status == "paid"
    assert first.sepay_transaction_id == "sepay-txn-1"
    assert persisted_user is not None
    assert persisted_user.credit_balance == 2_400
    assert len(transactions) == 1
    assert transactions[0].kind == "topup"
    assert transactions[0].delta == 2_400
    assert transactions[0].reference_id == order.id


@pytest.mark.asyncio
async def test_mark_order_paid_expires_stale_pending_order_without_crediting(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEPAY_ACCOUNT_NUMBER", "0123456789")
    monkeypatch.setenv("SEPAY_ACCOUNT_BANK_BIN", "MB")
    monkeypatch.setenv("USD_TO_VND_RATE", "25000")
    get_settings.cache_clear()
    user = await create_user(session_factory, email="expired-order@example.com")

    async with session_factory() as session:
        order = await create_order(session, user=user, pack_id="student")
        order.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await session.commit()

        paid_order = await mark_order_paid(
            session,
            reference_code=order.reference_code,
            sepay_transaction_id="sepay-expired-1",
            paid_amount_vnd=order.vnd_amount,
        )
        persisted_user = await session.get(User, user.id)
        transactions = list(
            (
                await session.execute(
                    select(CreditTransaction).where(CreditTransaction.user_id == user.id)
                )
            ).scalars()
        )

    assert paid_order is None
    assert order.status == "expired"
    assert persisted_user is not None
    assert persisted_user.credit_balance == 0
    assert transactions == []


@pytest.mark.asyncio
async def test_payments_routes_list_packs_create_and_fetch_order_and_balance(
    payments_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await create_user(session_factory, email="payments-api@example.com")
    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    packs_response = await payments_client.get("/payments/packs", headers=headers)
    assert packs_response.status_code == 200
    packs = packs_response.json()
    assert any(pack["id"] == "student" and pack["vnd_amount"] == 200_000 for pack in packs)

    create_response = await payments_client.post(
        "/payments/orders",
        headers=headers,
        json={"pack_id": "student"},
    )
    assert create_response.status_code == 201
    order_payload = create_response.json()
    assert order_payload["pack_id"] == "student"
    assert order_payload["status"] == "pending"
    assert order_payload["vnd_amount"] == 200_000
    assert order_payload["qr_url"]

    get_response = await payments_client.get(
        f"/payments/orders/{order_payload['id']}",
        headers=headers,
    )
    assert get_response.status_code == 200
    assert get_response.json()["reference_code"] == order_payload["reference_code"]

    balance_response = await payments_client.get("/payments/balance", headers=headers)
    assert balance_response.status_code == 200
    balance_payload = balance_response.json()
    assert balance_payload["credit_balance"] == 0
    assert balance_payload["recent_transactions"] == []
