from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from backend.api.dependencies import CurrentUser, DbSession
from backend.api.schemas.payments import (
    CreditPackRead,
    CreditTransactionRead,
    PaymentBalanceRead,
    PaymentOrderCreate,
    PaymentOrderRead,
)
from backend.config import get_settings
from backend.db.models import CreditTransaction, PaymentOrder
from backend.services.fx import usd_cents_to_vnd
from backend.services.payment_orders import UnknownCreditPackError, create_order

router = APIRouter(prefix="/payments", tags=["payments"])


async def get_owned_order_or_404(
    session: DbSession,
    *,
    user_id: str,
    order_id: str,
) -> PaymentOrder:
    result = await session.execute(
        select(PaymentOrder).where(
            PaymentOrder.id == order_id,
            PaymentOrder.user_id == user_id,
        )
    )
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment order not found.")
    return order


@router.get("/packs", response_model=list[CreditPackRead])
async def list_payment_packs(current_user: CurrentUser) -> list[CreditPackRead]:
    """List configured credit packs with their current VND conversion."""

    _ = current_user
    settings = get_settings()
    return [
        CreditPackRead.from_pack(
            pack,
            vnd_amount=usd_cents_to_vnd(pack.usd_cents, settings.usd_to_vnd_rate),
        )
        for pack in settings.credit_pack_catalog
    ]


@router.post("/orders", response_model=PaymentOrderRead, status_code=status.HTTP_201_CREATED)
async def create_payment_order(
    payload: PaymentOrderCreate,
    session: DbSession,
    current_user: CurrentUser,
    response: Response,
) -> PaymentOrderRead:
    """Create a pending Sepay payment order for the authenticated user."""

    try:
        order = await create_order(session, user=current_user, pack_id=payload.pack_id)
    except UnknownCreditPackError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    response.headers["Location"] = f"/payments/orders/{order.id}"
    return PaymentOrderRead.from_order(order)


@router.get("/orders/{order_id}", response_model=PaymentOrderRead)
async def get_payment_order(
    order_id: str,
    session: DbSession,
    current_user: CurrentUser,
) -> PaymentOrderRead:
    """Fetch one owned payment order."""

    order = await get_owned_order_or_404(session, user_id=current_user.id, order_id=order_id)
    return PaymentOrderRead.from_order(order)


@router.get("/balance", response_model=PaymentBalanceRead)
async def get_payment_balance(
    session: DbSession,
    current_user: CurrentUser,
) -> PaymentBalanceRead:
    """Return the current user balance and recent ledger entries."""

    transactions = list(
        (
            await session.execute(
                select(CreditTransaction)
                .where(CreditTransaction.user_id == current_user.id)
                .order_by(CreditTransaction.created_at.desc(), CreditTransaction.id.desc())
                .limit(20)
            )
        ).scalars()
    )
    return PaymentBalanceRead(
        credit_balance=current_user.credit_balance,
        is_unlimited=current_user.email.lower() in get_settings().admin_email_set,
        recent_transactions=[
            CreditTransactionRead.from_transaction(transaction) for transaction in transactions
        ],
    )
