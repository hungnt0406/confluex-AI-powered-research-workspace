from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from backend.api.dependencies import DbSession
from backend.api.schemas.auth import AuthRequest, AuthResponse, UserRead
from backend.db.models import User
from backend.security import create_access_token, hash_password, verify_password

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

    existing_user = await session.execute(select(User).where(User.email == payload.email))
    if existing_user.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with that email already exists.",
        )

    user = User(email=payload.email, hashed_password=hash_password(payload.password))
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return build_auth_response(user)


@router.post("/login", response_model=AuthResponse)
async def login_user(payload: AuthRequest, session: DbSession) -> AuthResponse:
    """Authenticate a user and return a JWT."""

    result = await session.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    return build_auth_response(user)
