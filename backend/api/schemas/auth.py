from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AuthRequest(BaseModel):
    """Request body for register and login endpoints."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class GoogleAuthRequest(BaseModel):
    """Request body for Google Sign-In endpoint."""

    credential: str = Field(min_length=1, description="Google ID token from GIS callback")


class UserRead(BaseModel):
    """Serialized user payload."""

    id: str
    email: EmailStr
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuthResponse(BaseModel):
    """JWT response payload."""

    access_token: str
    token_type: str
    user: UserRead
