import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import cast

import jwt

from backend.config import get_settings

HASH_NAME = "sha256"
ITERATIONS = 600_000
SALT_BYTES = 16
KEY_BYTES = 32


def hash_password(password: str) -> str:
    """Hash a plain-text password."""

    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        HASH_NAME,
        password.encode("utf-8"),
        salt,
        ITERATIONS,
        dklen=KEY_BYTES,
    )
    encoded_salt = base64.urlsafe_b64encode(salt).decode("ascii")
    encoded_digest = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"pbkdf2_{HASH_NAME}${ITERATIONS}${encoded_salt}${encoded_digest}"


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against its hash."""

    try:
        algorithm, iteration_value, encoded_salt, encoded_digest = hashed_password.split(
            "$", maxsplit=3
        )
    except ValueError:
        return False

    if algorithm != f"pbkdf2_{HASH_NAME}":
        return False

    salt = base64.urlsafe_b64decode(encoded_salt.encode("ascii"))
    expected_digest = base64.urlsafe_b64decode(encoded_digest.encode("ascii"))
    candidate_digest = hashlib.pbkdf2_hmac(
        HASH_NAME,
        password.encode("utf-8"),
        salt,
        int(iteration_value),
        dklen=len(expected_digest),
    )
    return hmac.compare_digest(candidate_digest, expected_digest)


def create_access_token(user_id: str) -> str:
    """Create a signed JWT for the authenticated user."""

    settings = get_settings()
    expires_at = datetime.now(tz=UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": user_id,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, object]:
    """Decode and validate a signed JWT."""

    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    return cast(dict[str, object], payload)
