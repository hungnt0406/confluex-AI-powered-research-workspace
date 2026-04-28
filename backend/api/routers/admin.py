from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from backend.api.dependencies import AdminUser, CurrentUser, DbSession
from backend.api.schemas.admin import (
    AdminAccessRead,
    AdminTokenUsageRead,
    AdminUsageEventRow,
    AdminUsageProjectRow,
    AdminUsageUserRow,
)
from backend.api.schemas.projects import TokenUsageBreakdownRow, TokenUsageDailyRow
from backend.config import get_settings
from backend.services.ai_usage import summarize_admin_usage

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/access", response_model=AdminAccessRead)
async def get_admin_access(current_user: CurrentUser) -> AdminAccessRead:
    """Return whether the authenticated user is on the admin allowlist."""

    return AdminAccessRead(
        is_admin=current_user.email.lower() in get_settings().admin_email_set,
    )


@router.get("/token-usage", response_model=AdminTokenUsageRead)
async def get_admin_token_usage(
    session: DbSession,
    _: AdminUser,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    user_id: Annotated[str | None, Query()] = None,
    project_id: Annotated[str | None, Query()] = None,
) -> AdminTokenUsageRead:
    """Return global provider-reported token usage aggregates for admins."""

    summary = await summarize_admin_usage(
        session=session,
        date_from=date_from,
        date_to=date_to,
        user_id=user_id,
        project_id=project_id,
    )
    return AdminTokenUsageRead(
        date_from=date_from,
        date_to=date_to,
        user_id=user_id,
        project_id=project_id,
        total_tokens=summary.total_tokens,
        prompt_tokens=summary.prompt_tokens,
        completion_tokens=summary.completion_tokens,
        reasoning_tokens=summary.reasoning_tokens,
        cached_tokens=summary.cached_tokens,
        cost_credits=summary.cost_credits,
        request_count=summary.request_count,
        by_feature=[
            TokenUsageBreakdownRow(
                key=row.key,
                total_tokens=row.total_tokens,
                prompt_tokens=row.prompt_tokens,
                completion_tokens=row.completion_tokens,
                cost_credits=row.cost_credits,
                request_count=row.request_count,
            )
            for row in summary.by_feature
        ],
        by_model=[
            TokenUsageBreakdownRow(
                key=row.key,
                total_tokens=row.total_tokens,
                prompt_tokens=row.prompt_tokens,
                completion_tokens=row.completion_tokens,
                cost_credits=row.cost_credits,
                request_count=row.request_count,
            )
            for row in summary.by_model
        ],
        by_day=[
            TokenUsageDailyRow(
                day=row.day,
                total_tokens=row.total_tokens,
                prompt_tokens=row.prompt_tokens,
                completion_tokens=row.completion_tokens,
                cost_credits=row.cost_credits,
                request_count=row.request_count,
            )
            for row in summary.by_day
        ],
        by_user=[
            AdminUsageUserRow(
                user_id=row.user_id,
                user_email=row.user_email,
                total_tokens=row.total_tokens,
                prompt_tokens=row.prompt_tokens,
                completion_tokens=row.completion_tokens,
                cost_credits=row.cost_credits,
                request_count=row.request_count,
            )
            for row in summary.by_user
        ],
        by_project=[
            AdminUsageProjectRow(
                project_id=row.project_id,
                project_title=row.project_title,
                user_id=row.user_id,
                user_email=row.user_email,
                total_tokens=row.total_tokens,
                prompt_tokens=row.prompt_tokens,
                completion_tokens=row.completion_tokens,
                cost_credits=row.cost_credits,
                request_count=row.request_count,
            )
            for row in summary.by_project
        ],
        recent_events=[
            AdminUsageEventRow(
                id=row.id,
                created_at=row.created_at,
                user_id=row.user_id,
                user_email=row.user_email,
                project_id=row.project_id,
                project_title=row.project_title,
                provider=row.provider,
                endpoint=row.endpoint,
                feature=row.feature,
                model=row.model,
                status=row.status,
                prompt_tokens=row.prompt_tokens,
                completion_tokens=row.completion_tokens,
                total_tokens=row.total_tokens,
                reasoning_tokens=row.reasoning_tokens,
                cached_tokens=row.cached_tokens,
                cost_credits=row.cost_credits,
            )
            for row in summary.recent_events
        ],
    )
