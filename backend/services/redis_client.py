"""Optional async Redis client used by stores that opt in.

If the `redis` package is not installed, or `REDIS_URL` is unset, `get_redis()`
returns `None` and callers fall back to in-memory implementations.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.config import get_settings

logger = logging.getLogger(__name__)

_cached_client: Any | None = None
_cached_url: str | None = None
_warned_missing_package = False


async def get_redis() -> Any | None:
    """Return a cached `redis.asyncio.Redis` client, or None if unavailable."""

    global _cached_client, _cached_url, _warned_missing_package
    settings = get_settings()
    url = settings.redis_url
    if not url:
        return None
    if _cached_client is not None and _cached_url == url:
        return _cached_client
    try:
        from redis.asyncio import Redis  # type: ignore[import-not-found]
    except ImportError:
        if not _warned_missing_package:
            logger.warning(
                "REDIS_URL is set but the `redis` package is not installed; "
                "falling back to the in-memory chat session store."
            )
            _warned_missing_package = True
        return None

    _cached_client = Redis.from_url(url, decode_responses=True)
    _cached_url = url
    return _cached_client


async def close_redis() -> None:
    """Close the cached Redis client, if any."""

    global _cached_client, _cached_url
    if _cached_client is not None:
        try:
            await _cached_client.aclose()
        except Exception:  # noqa: BLE001 - best effort close
            logger.debug("Failed to close Redis client cleanly.", exc_info=True)
    _cached_client = None
    _cached_url = None
