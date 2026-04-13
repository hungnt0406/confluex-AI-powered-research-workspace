import math
import re
from collections.abc import Sequence

TITLE_NORMALIZATION_PATTERN = re.compile(r"[^a-z0-9\s]+")
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def has_live_api_key(api_key: str | None) -> bool:
    """Return whether an API key looks usable for a live request."""

    if api_key is None:
        return False

    normalized_key = api_key.strip().lower()
    if not normalized_key:
        return False

    blocked_prefixes = ("placeholder", "test-", "dummy", "changeme")
    if normalized_key.startswith(blocked_prefixes):
        return False

    return "..." not in normalized_key


def normalize_title(title: str) -> str:
    """Normalize a title for duplicate detection."""

    lowered_title = title.lower().strip()
    without_punctuation = TITLE_NORMALIZATION_PATTERN.sub(" ", lowered_title)
    return " ".join(without_punctuation.split())


def tokenize_text(text: str) -> list[str]:
    """Tokenize text into lowercase alphanumeric tokens."""

    return TOKEN_PATTERN.findall(text.lower())


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Compute cosine similarity between two vectors."""

    if len(left) != len(right):
        raise ValueError("Vector dimensions must match.")

    dot_product = sum(
        left_value * right_value
        for left_value, right_value in zip(left, right, strict=True)
    )
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))

    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0

    return dot_product / (left_norm * right_norm)
