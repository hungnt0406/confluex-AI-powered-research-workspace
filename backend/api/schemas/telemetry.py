from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

MessageFeedbackAction = Literal["like", "dislike", "copy"]
MessageFeedbackSurface = Literal[
    "chat",
    "deep_search",
    "deep_research_max",
    "writer",
    "paper_conversation",
]


class MessageFeedbackCreate(BaseModel):
    """Payload for recording a like/dislike/copy interaction."""

    action: MessageFeedbackAction
    surface: MessageFeedbackSurface
    message_id: str | None = Field(default=None, max_length=64)
    project_id: str | None = Field(default=None, max_length=36)
    content_preview: str | None = Field(default=None, max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageFeedbackRead(BaseModel):
    """Stored feedback event."""

    id: str
    action: MessageFeedbackAction
    surface: str
    message_id: str | None
    project_id: str | None
    created_at: datetime
