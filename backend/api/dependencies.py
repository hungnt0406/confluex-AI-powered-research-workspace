from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.pipeline import LiteraturePipelineService
from backend.db.models import User
from backend.db.session import get_db_session
from backend.security import decode_access_token
from backend.services.paper_citations import PaperCitationService
from backend.services.paper_conversations import PaperConversationService
from backend.services.reference_files import ReferenceFileService
from backend.services.writer_outputs import WriterOutputService

bearer_scheme = HTTPBearer(auto_error=False)
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


async def get_current_user(
    session: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    """Resolve the authenticated user from the bearer token."""

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
        )

    try:
        payload = decode_access_token(credentials.credentials)
        subject = payload.get("sub")
        if not isinstance(subject, str):
            raise TypeError("Token subject must be a string.")
        user_id = subject
    except (jwt.InvalidTokenError, KeyError, TypeError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        ) from error

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user no longer exists.",
        )

    return user


def get_pipeline_service() -> LiteraturePipelineService:
    """Return the default literature pipeline service."""

    return LiteraturePipelineService()


def get_reference_file_service() -> ReferenceFileService:
    """Return the default reference file service."""

    return ReferenceFileService()


def get_paper_conversation_service() -> PaperConversationService:
    """Return the default paper conversation service."""

    return PaperConversationService()


def get_paper_citation_service() -> PaperCitationService:
    """Return the default paper citation service."""

    return PaperCitationService()


def get_writer_output_service() -> WriterOutputService:
    """Return the default writer output service."""

    return WriterOutputService()


CurrentUser = Annotated[User, Depends(get_current_user)]
PipelineServiceDependency = Annotated[LiteraturePipelineService, Depends(get_pipeline_service)]
ReferenceFileServiceDependency = Annotated[
    ReferenceFileService,
    Depends(get_reference_file_service),
]
PaperConversationServiceDependency = Annotated[
    PaperConversationService,
    Depends(get_paper_conversation_service),
]
PaperCitationServiceDependency = Annotated[
    PaperCitationService,
    Depends(get_paper_citation_service),
]
WriterOutputServiceDependency = Annotated[
    WriterOutputService,
    Depends(get_writer_output_service),
]
