import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.api.dependencies import DbSession
from backend.api.schemas.auth import AuthRequest, AuthResponse, GoogleAuthRequest, UserRead
from backend.config import get_settings
from backend.db.models import User
from backend.security import create_access_token, hash_password, verify_password
from backend.services.credits import credit

router = APIRouter(prefix="/auth", tags=["auth"])


def build_auth_response(user: User) -> AuthResponse:
    """Return a token payload for the authenticated user."""

    return AuthResponse(
        access_token=create_access_token(user.id),
        token_type="bearer",
        user=UserRead.model_validate(user),
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register_user(payload: AuthRequest, session: DbSession) -> AuthResponse:
    """Register a new user and immediately return an access token."""

    if not payload.agreed_to_terms:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must agree to the Terms of Service to create an account.",
        )

    existing_user = await session.execute(select(User).where(User.email == payload.email))
    if existing_user.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with that email already exists.",
        )

    user = User(email=payload.email, hashed_password=hash_password(payload.password))
    session.add(user)
    await session.flush()
    await credit(
        session,
        user_id=user.id,
        delta=get_settings().signup_bonus_credits,
        kind="grant",
        metadata={"reason": "signup_bonus"},
    )
    await session.commit()
    await session.refresh(user)
    return build_auth_response(user)


@router.post("/login", response_model=AuthResponse)
async def login_user(payload: AuthRequest, session: DbSession) -> AuthResponse:
    """Authenticate a user and return a JWT."""

    result = await session.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if (
        user is None
        or user.hashed_password is None
        or not verify_password(payload.password, user.hashed_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    return build_auth_response(user)


@router.post("/google", response_model=AuthResponse)
async def google_login(payload: GoogleAuthRequest, session: DbSession) -> AuthResponse:
    """Verify a Google ID token and return a JWT.

    If no user exists for the Google account, one is auto-registered.
    If a user with the same email already exists (email/password flow),
    the Google identity is linked to that account.
    """

    settings = get_settings()
    if not settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google Sign-In is not configured on this server.",
        )

    # Verify the ID token with Google's public keys.
    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token

        idinfo = id_token.verify_oauth2_token(
            payload.credential,
            google_requests.Request(),
            settings.google_client_id,
        )  # type: ignore[no-untyped-call]
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google credential.",
        ) from None
    except Exception:
        logging.getLogger(__name__).exception("Google token verification failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google authentication failed. Please try again.",
        ) from None

    google_sub: str = idinfo["sub"]
    email: str = idinfo.get("email", "")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google account does not have an email address.",
        )

    # Find existing user by google_sub or email.
    result = await session.execute(
        select(User).where((User.google_sub == google_sub) | (User.email == email))
    )
    user = result.scalar_one_or_none()

    if user is None:
        if not payload.agreed_to_terms:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Account not found. Please switch to Register and agree to the Terms of Service to create one.",
            )
        # Auto-register a new Google user (no password needed).
        # Handle race condition: if a concurrent request already inserted
        # this user, catch the IntegrityError and re-fetch.
        try:
            user = User(
                email=email,
                hashed_password=None,
                auth_provider="google",
                google_sub=google_sub,
            )
            session.add(user)
            await session.flush()
            await credit(
                session,
                user_id=user.id,
                delta=settings.signup_bonus_credits,
                kind="grant",
                metadata={"reason": "signup_bonus"},
            )
            await session.commit()
            await session.refresh(user)
        except IntegrityError:
            await session.rollback()
            result = await session.execute(
                select(User).where(
                    (User.google_sub == google_sub) | (User.email == email)
                )
            )
            user = result.scalar_one_or_none()
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Account creation failed. Please try again.",
                ) from None
    elif user.google_sub is None:
        # Link existing email/password user to their Google identity.
        user.google_sub = google_sub
        user.auth_provider = "google"
        await session.commit()
        await session.refresh(user)

    return build_auth_response(user)
