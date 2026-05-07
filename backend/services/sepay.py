from __future__ import annotations

import secrets
from collections.abc import Mapping
from urllib.parse import urlencode

from backend.config import get_settings


def build_vietqr_payload(
    account: str,
    bank_bin: str,
    amount_vnd: int,
    description: str,
) -> str:
    """Build a hosted VietQR image URL for a Sepay-compatible transfer."""

    query = urlencode(
        {
            "acc": account.strip(),
            "bank": bank_bin.strip(),
            "amount": amount_vnd,
            "des": description.strip(),
        }
    )
    return f"https://qr.sepay.vn/img?{query}"


def verify_webhook_auth(headers: Mapping[str, str]) -> bool:
    """Verify Sepay webhook authorization headers."""

    expected_key = (get_settings().sepay_webhook_api_key or "").strip()
    if not expected_key:
        return False

    authorization = headers.get("Authorization") or headers.get("authorization") or ""
    scheme, _, presented_key = authorization.strip().partition(" ")
    if scheme.lower() != "apikey" or not presented_key:
        return False

    return secrets.compare_digest(presented_key.strip(), expected_key)
