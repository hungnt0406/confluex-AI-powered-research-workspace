from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.pipeline import LiteraturePipelineService
from backend.config import get_settings
from backend.db.models import CreditTransaction, User
from backend.db.session import get_db_session
from backend.security import decode_access_token
from backend.services.credits import InsufficientCreditsError, credit, debit
from backend.services.deep_search import DeepSearchService
from backend.services.paper_citations import PaperCitationService
from backend.services.paper_conversations import PaperConversationService
from backend.services.project_conversations import ProjectConversationService
from backend.services.reference_files import ReferenceFileService
from backend.services.writer_outputs import WriterOutputService

bearer_scheme = HTTPBearer(auto_error=False)
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


class InsufficientCreditsHttpError(Exception):
    """Raised when a paid feature is requested without enough credits."""

    def __init__(self, *, required: int, balance: int):
        super().__init__("Insufficient credits.")
        self.required = required
        self.balance = balance


@dataclass
class CreditDebitGuard:
    """Track one pre-debited feature charge and optionally refund it on failure."""

    session: AsyncSession
    transaction_id: str
    user_id: str
    amount: int
    feature: str
    finalized: bool = False

    async def commit(self, *, reference_id: str | None = None) -> None:
        """Finalize the debit and optionally attach a domain reference id."""

        if self.finalized:
            return
        if self.amount <= 0:
            self.finalized = True
            return
        if reference_id is not None:
            transaction = await self.session.get(CreditTransaction, self.transaction_id)
            if transaction is not None:
                transaction.reference_id = reference_id
                await self.session.commit()
        self.finalized = True

    async def rollback(self) -> None:
        """Refund a pre-debit after the guarded operation fails."""

        if self.finalized:
            return

        await self.session.rollback()
        if self.amount <= 0:
            self.finalized = True
            return

        await credit(
            self.session,
            user_id=self.user_id,
            delta=self.amount,
            kind="refund",
            feature=self.feature,
            reference_id=self.transaction_id,
            metadata={"refunded_transaction_id": self.transaction_id},
        )
        await self.session.commit()
        self.finalized = True


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


async def get_current_admin_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Resolve and authorize an allowlisted admin user."""

    if current_user.email.lower() not in get_settings().admin_email_set:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access is required.",
        )
    return current_user


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


def get_project_conversation_service() -> ProjectConversationService:
    """Return the default project conversation service."""

    return ProjectConversationService()


def get_writer_output_service() -> WriterOutputService:
    """Return the default writer output service."""

    return WriterOutputService()


def get_deep_search_service() -> DeepSearchService:
    """Return the default deep search service."""

    return DeepSearchService()


async def require_credits(
    amount: int,
    feature: str,
    *,
    current_user: User,
    session: AsyncSession,
) -> CreditDebitGuard:
    """Pre-debit a user's balance before running a paid feature."""

    if current_user.email.lower() in get_settings().admin_email_set:
        return CreditDebitGuard(
            session=session,
            transaction_id="",
            user_id=current_user.id,
            amount=0,
            feature=feature,
        )

    try:
        transaction = await debit(
            session,
            user_id=current_user.id,
            amount=amount,
            feature=feature,
        )
        await session.commit()
        return CreditDebitGuard(
            session=session,
            transaction_id=transaction.id,
            user_id=current_user.id,
            amount=amount,
            feature=feature,
        )
    except InsufficientCreditsError as error:
        await session.rollback()
        raise InsufficientCreditsHttpError(
            required=error.required,
            balance=error.balance,
        ) from error


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(get_current_admin_user)]
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
ProjectConversationServiceDependency = Annotated[
    ProjectConversationService,
    Depends(get_project_conversation_service),
]
WriterOutputServiceDependency = Annotated[
    WriterOutputService,
    Depends(get_writer_output_service),
]
DeepSearchServiceDependency = Annotated[
    DeepSearchService,
    Depends(get_deep_search_service),
]
