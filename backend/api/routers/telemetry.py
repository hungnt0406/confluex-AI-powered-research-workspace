"""Lightweight client telemetry endpoints (like/dislike/copy)."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from backend.api.dependencies import CurrentUser, DbSession
from backend.api.schemas.telemetry import MessageFeedbackCreate, MessageFeedbackRead
from backend.db.models import MessageFeedbackEvent, Project

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.post(
    "/message-feedback",
    response_model=MessageFeedbackRead,
    status_code=status.HTTP_201_CREATED,
)
async def record_message_feedback(
    payload: MessageFeedbackCreate,
    session: DbSession,
    current_user: CurrentUser,
) -> MessageFeedbackRead:
    """Persist a single like/dislike/copy interaction for later analysis."""

    project_id = payload.project_id
    if project_id:
        project = await session.scalar(
            select(Project).where(
                Project.id == project_id,
                Project.user_id == current_user.id,
            )
        )
        if project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found.",
            )

    event = MessageFeedbackEvent(
        user_id=current_user.id,
        project_id=project_id,
        message_id=payload.message_id,
        surface=payload.surface,
        action=payload.action,
        content_preview=payload.content_preview,
        metadata_json=payload.metadata,
    )
    session.add(event)
    await session.flush()
    await session.commit()

    return MessageFeedbackRead(
        id=event.id,
        action=event.action,  # type: ignore[arg-type]
        surface=event.surface,
        message_id=event.message_id,
        project_id=event.project_id,
        created_at=event.created_at,
    )
