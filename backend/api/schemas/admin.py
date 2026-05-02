from datetime import date, datetime

from pydantic import BaseModel

from backend.api.schemas.projects import TokenUsageBreakdownRow, TokenUsageDailyRow


class AdminAccessRead(BaseModel):
    """Current user's admin access state."""

    is_admin: bool


class AdminUsageUserRow(BaseModel):
    """Aggregated usage for one user."""

    user_id: str
    user_email: str
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    cost_credits: float | None
    request_count: int


class AdminUsageProjectRow(BaseModel):
    """Aggregated usage for one project."""

    project_id: str
    project_title: str
    user_id: str
    user_email: str
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    cost_credits: float | None
    request_count: int


class AdminUsageEventRow(BaseModel):
    """Recent token usage event with owner and project context."""

    id: str
    created_at: datetime
    user_id: str
    user_email: str
    project_id: str
    project_title: str
    provider: str
    endpoint: str
    feature: str
    model: str | None
    status: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    reasoning_tokens: int
    cached_tokens: int
    cost_credits: float | None
    user_prompt: str | None


class AdminTokenUsageRead(BaseModel):
    """Global provider-reported AI token usage summary for admins."""

    date_from: date | None
    date_to: date | None
    user_id: str | None
    project_id: str | None
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    cached_tokens: int
    cost_credits: float | None
    request_count: int
    by_feature: list[TokenUsageBreakdownRow]
    by_model: list[TokenUsageBreakdownRow]
    by_day: list[TokenUsageDailyRow]
    by_user: list[AdminUsageUserRow]
    by_project: list[AdminUsageProjectRow]
    recent_events: list[AdminUsageEventRow]
