import re

from fastapi import APIRouter, Header, HTTPException, status

from backend.api.dependencies import DbSession
from backend.api.schemas.payments import SepayWebhookPayload, SepayWebhookResponse
from backend.services.payment_orders import mark_order_paid
from backend.services.sepay import verify_webhook_auth

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

REFERENCE_CODE_PATTERN = re.compile(r"ORD[A-Z0-9]{6,12}")


def extract_reference_code(content: str | None) -> str | None:
    """Extract one payment order reference code from Sepay transfer content."""

    if not content:
        return None
    match = REFERENCE_CODE_PATTERN.search(content.upper())
    if match is None:
        return None
    return match.group(0)


@router.post("/sepay", response_model=SepayWebhookResponse, response_model_exclude_none=True)
async def receive_sepay_webhook(
    payload: SepayWebhookPayload,
    session: DbSession,
    authorization: str | None = Header(default=None),
) -> SepayWebhookResponse:
    """Handle a Sepay bank-transfer notification."""

    if not verify_webhook_auth({"Authorization": authorization or ""}):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook authorization.",
        )

    if payload.transfer_type != "in" or not payload.content:
        return SepayWebhookResponse(matched=False)

    reference_code = extract_reference_code(payload.content)
    if reference_code is None or payload.transfer_amount is None:
        return SepayWebhookResponse(matched=False)

    order = await mark_order_paid(
        session,
        reference_code=reference_code,
        sepay_transaction_id=payload.transaction_id,
        paid_amount_vnd=payload.transfer_amount,
    )
    if order is None:
        return SepayWebhookResponse(matched=False)

    return SepayWebhookResponse(matched=True, status=order.status, order_id=order.id)
