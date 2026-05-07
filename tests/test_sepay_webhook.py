import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.api.dependencies import get_db_session
from backend.config import get_settings
from backend.db.models import CreditTransaction, User
from backend.main import create_app
from backend.security import hash_password
from backend.services.payment_orders import create_order


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
async def webhook_client(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncClient:
    monkeypatch.setenv("SEPAY_WEBHOOK_API_KEY", "test-webhook-key")
    monkeypatch.setenv("SEPAY_ACCOUNT_NUMBER", "0123456789")
    monkeypatch.setenv("SEPAY_ACCOUNT_BANK_BIN", "MB")
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
async def test_sepay_webhook_rejects_wrong_authorization_header(
    webhook_client: AsyncClient,
) -> None:
    response = await webhook_client.post(
        "/webhooks/sepay",
        headers={"Authorization": "Apikey wrong-key"},
        json={"id": "txn-wrong-key", "transferType": "in", "content": "ORDABC123456"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid webhook authorization."}


@pytest.mark.asyncio
async def test_sepay_webhook_ignores_outgoing_transfers(
    webhook_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await create_user(session_factory, email="outgoing@example.com")

    async with session_factory() as session:
        await create_order(session, user=user, pack_id="student")

    response = await webhook_client.post(
        "/webhooks/sepay",
        headers={"Authorization": "Apikey test-webhook-key"},
        json={
            "id": "txn-out-1",
            "transferType": "out",
            "content": "Transfer ORDABC123456",
            "transferAmount": 200000,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"matched": False}


@pytest.mark.asyncio
async def test_sepay_webhook_returns_200_for_unknown_reference_code(
    webhook_client: AsyncClient,
) -> None:
    response = await webhook_client.post(
        "/webhooks/sepay",
        headers={"Authorization": "Apikey test-webhook-key"},
        json={
            "id": "txn-unknown-1",
            "transferType": "in",
            "content": "Thanh toan ORDUNKNOWN99",
            "transferAmount": 200000,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"matched": False}


@pytest.mark.asyncio
async def test_sepay_webhook_marks_matching_order_paid_and_credits_balance(
    webhook_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await create_user(session_factory, email="webhook-paid@example.com")

    async with session_factory() as session:
        order = await create_order(session, user=user, pack_id="student")

    response = await webhook_client.post(
        "/webhooks/sepay",
        headers={"Authorization": "Apikey test-webhook-key"},
        json={
            "id": "txn-paid-1",
            "gateway": "MBBank",
            "transactionDate": "2026-05-07 10:00:00",
            "accountNumber": "0123456789",
            "content": f"Nap tien cho {order.reference_code} vao tai khoan",
            "transferAmount": order.vnd_amount,
            "transferType": "in",
        },
    )

    assert response.status_code == 200
    assert response.json()["matched"] is True
    assert response.json()["status"] == "paid"

    async with session_factory() as session:
        persisted_user = await session.get(User, user.id)
        transactions = list(
            (
                await session.execute(
                    select(CreditTransaction).where(CreditTransaction.user_id == user.id)
                )
            ).scalars()
        )

    assert persisted_user is not None
    assert persisted_user.credit_balance == 800
    assert len(transactions) == 1
    assert transactions[0].kind == "topup"
    assert transactions[0].delta == 800
