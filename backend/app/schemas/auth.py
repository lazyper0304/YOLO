"""Auth schemas: register, login, user info."""

from pydantic import BaseModel, Field, EmailStr


class RegisterRequest(BaseModel):
    """User registration request."""
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100)


class LoginRequest(BaseModel):
    """User login request."""
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=100)


class TokenResponse(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Public user info response."""
    id: int
    username: str
    email: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True
