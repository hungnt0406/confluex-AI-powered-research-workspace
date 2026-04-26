from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AIUsageEvent


@dataclass(frozen=True)
class CollectedAIUsageEvent:
    """Provider-reported usage captured during one request."""

    provider: str
    endpoint: str
    feature: str
    model: str | None
    status: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None
    cached_tokens: int | None = None
    cost_credits: float | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UsageBreakdownRow:
    key: str
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    cost_credits: float | None
    request_count: int


@dataclass(frozen=True)
class UsageDailyRow:
    day: date
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    cost_credits: float | None
    request_count: int


@dataclass(frozen=True)
class ProjectTokenUsageSummary:
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    cached_tokens: int
    cost_credits: float | None
    request_count: int
    by_feature: list[UsageBreakdownRow]
    by_model: list[UsageBreakdownRow]
    by_day: list[UsageDailyRow]


_request_usage_events: ContextVar[list[CollectedAIUsageEvent] | None] = ContextVar(
    "request_usage_events",
    default=None,
)


def start_usage_collection() -> None:
    """Reset the current request collector."""

    _request_usage_events.set([])


def collect_openrouter_usage(
    *,
    endpoint: str,
    feature: str,
    model: str | None,
    response_payload: dict[str, Any],
    status: str = "success",
    metadata: dict[str, Any] | None = None,
) -> None:
    """Record provider usage from a parsed OpenRouter response payload."""

    usage = response_payload.get("usage")
    if not isinstance(usage, dict):
        usage = {}

    metadata_json = dict(metadata or {})
    metadata_json.update(_compact_usage_metadata(usage))

    event = CollectedAIUsageEvent(
        provider="openrouter",
        endpoint=endpoint,
        feature=feature,
        model=model,
        status=status,
        prompt_tokens=_int_or_none(usage.get("prompt_tokens")),
        completion_tokens=_int_or_none(usage.get("completion_tokens")),
        total_tokens=_int_or_none(usage.get("total_tokens")),
        reasoning_tokens=_extract_reasoning_tokens(usage),
        cached_tokens=_extract_cached_tokens(usage),
        cost_credits=_float_or_none(_first_present(usage, "cost", "total_cost", "cost_credits")),
        metadata_json=metadata_json,
    )
    _append_event(event)


async def flush_usage_events(
    *,
    session: AsyncSession,
    user_id: str,
    project_id: str,
) -> int:
    """Persist and clear usage events collected during the current request."""

    collected = _request_usage_events.get()
    if not collected:
        _request_usage_events.set([])
        return 0

    for event in collected:
        session.add(
            AIUsageEvent(
                user_id=user_id,
                project_id=project_id,
                provider=event.provider,
                endpoint=event.endpoint,
                feature=event.feature,
                model=event.model,
                status=event.status,
                prompt_tokens=event.prompt_tokens,
                completion_tokens=event.completion_tokens,
                total_tokens=event.total_tokens,
                reasoning_tokens=event.reasoning_tokens,
                cached_tokens=event.cached_tokens,
                cost_credits=event.cost_credits,
                metadata_json=event.metadata_json,
            )
        )

    await session.commit()
    count = len(collected)
    _request_usage_events.set([])
    return count


async def summarize_project_usage(
    *,
    session: AsyncSession,
    project_id: str,
) -> ProjectTokenUsageSummary:
    """Aggregate persisted usage for one project."""

    totals_result = await session.execute(
        select(
            func.coalesce(func.sum(AIUsageEvent.total_tokens), 0),
            func.coalesce(func.sum(AIUsageEvent.prompt_tokens), 0),
            func.coalesce(func.sum(AIUsageEvent.completion_tokens), 0),
            func.coalesce(func.sum(AIUsageEvent.reasoning_tokens), 0),
            func.coalesce(func.sum(AIUsageEvent.cached_tokens), 0),
            func.sum(AIUsageEvent.cost_credits),
            func.count(AIUsageEvent.id),
        ).where(AIUsageEvent.project_id == project_id)
    )
    totals = totals_result.one()

    return ProjectTokenUsageSummary(
        total_tokens=int(totals[0] or 0),
        prompt_tokens=int(totals[1] or 0),
        completion_tokens=int(totals[2] or 0),
        reasoning_tokens=int(totals[3] or 0),
        cached_tokens=int(totals[4] or 0),
        cost_credits=_float_or_none(totals[5]),
        request_count=int(totals[6] or 0),
        by_feature=await _breakdown(session=session, project_id=project_id, column=AIUsageEvent.feature),
        by_model=await _breakdown(session=session, project_id=project_id, column=AIUsageEvent.model),
        by_day=await _daily_breakdown(session=session, project_id=project_id),
    )


async def _breakdown(
    *,
    session: AsyncSession,
    project_id: str,
    column: Any,
) -> list[UsageBreakdownRow]:
    result = await session.execute(
        select(
            func.coalesce(column, "unknown"),
            func.coalesce(func.sum(AIUsageEvent.total_tokens), 0),
            func.coalesce(func.sum(AIUsageEvent.prompt_tokens), 0),
            func.coalesce(func.sum(AIUsageEvent.completion_tokens), 0),
            func.sum(AIUsageEvent.cost_credits),
            func.count(AIUsageEvent.id),
        )
        .where(AIUsageEvent.project_id == project_id)
        .group_by(column)
        .order_by(func.coalesce(func.sum(AIUsageEvent.total_tokens), 0).desc())
    )
    return [
        UsageBreakdownRow(
            key=str(row[0]),
            total_tokens=int(row[1] or 0),
            prompt_tokens=int(row[2] or 0),
            completion_tokens=int(row[3] or 0),
            cost_credits=_float_or_none(row[4]),
            request_count=int(row[5] or 0),
        )
        for row in result.all()
    ]


async def _daily_breakdown(
    *,
    session: AsyncSession,
    project_id: str,
) -> list[UsageDailyRow]:
    day_expression = func.date(AIUsageEvent.created_at)
    result = await session.execute(
        select(
            day_expression,
            func.coalesce(func.sum(AIUsageEvent.total_tokens), 0),
            func.coalesce(func.sum(AIUsageEvent.prompt_tokens), 0),
            func.coalesce(func.sum(AIUsageEvent.completion_tokens), 0),
            func.sum(AIUsageEvent.cost_credits),
            func.count(AIUsageEvent.id),
        )
        .where(AIUsageEvent.project_id == project_id)
        .group_by(day_expression)
        .order_by(day_expression.asc())
    )
    rows: list[UsageDailyRow] = []
    for row in result.all():
        day_value = row[0]
        if isinstance(day_value, date):
            parsed_day = day_value
        else:
            parsed_day = date.fromisoformat(str(day_value))
        rows.append(
            UsageDailyRow(
                day=parsed_day,
                total_tokens=int(row[1] or 0),
                prompt_tokens=int(row[2] or 0),
                completion_tokens=int(row[3] or 0),
                cost_credits=_float_or_none(row[4]),
                request_count=int(row[5] or 0),
            )
        )
    return rows


def _append_event(event: CollectedAIUsageEvent) -> None:
    collected = _request_usage_events.get()
    if collected is None:
        collected = []
        _request_usage_events.set(collected)
    collected.append(event)


def _compact_usage_metadata(usage: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key in ("prompt_tokens_details", "completion_tokens_details", "native_tokens", "is_byok"):
        value = usage.get(key)
        if isinstance(value, dict | list | str | int | float | bool) or value is None:
            metadata[key] = value
    return metadata


def _extract_reasoning_tokens(usage: dict[str, Any]) -> int | None:
    direct = _int_or_none(usage.get("reasoning_tokens"))
    if direct is not None:
        return direct
    details = usage.get("completion_tokens_details")
    if isinstance(details, dict):
        return _int_or_none(details.get("reasoning_tokens"))
    return None


def _extract_cached_tokens(usage: dict[str, Any]) -> int | None:
    direct = _int_or_none(usage.get("cached_tokens"))
    if direct is not None:
        return direct
    details = usage.get("prompt_tokens_details")
    if isinstance(details, dict):
        return _int_or_none(details.get("cached_tokens"))
    return None


def _int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None
