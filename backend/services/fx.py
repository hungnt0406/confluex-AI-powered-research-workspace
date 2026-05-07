from decimal import ROUND_HALF_UP, Decimal


def usd_cents_to_vnd(cents: int, rate: float) -> int:
    """Convert USD cents to VND and round to the nearest 1,000 VND."""

    if cents < 0:
        raise ValueError("cents must be non-negative.")
    if rate <= 0:
        raise ValueError("rate must be positive.")

    usd_amount = Decimal(cents) / Decimal(100)
    vnd_amount = usd_amount * Decimal(str(rate))
    rounded_thousands = (vnd_amount / Decimal(1000)).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )
    return int(rounded_thousands * Decimal(1000))
