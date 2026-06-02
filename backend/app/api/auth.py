"""Auth API routes: register, login, get current user."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, UserResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=dict)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user account."""
    auth_service = AuthService(db)
    user = await auth_service.register(req.username, req.email, req.password)
    return {"code": 0, "message": "ok", "data": {"id": user.id, "username": user.username}}


@router.post("/login", response_model=dict)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login and receive a JWT access token."""
    auth_service = AuthService(db)
    token = await auth_service.login(req.username, req.password)
    return {"code": 0, "message": "ok", "data": {"access_token": token, "token_type": "bearer"}}


@router.get("/me", response_model=dict)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get the currently authenticated user's profile."""
    user_data = UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        created_at=current_user.created_at.isoformat() if current_user.created_at else "",
        updated_at=current_user.updated_at.isoformat() if current_user.updated_at else "",
    )
    return {"code": 0, "message": "ok", "data": user_data.model_dump()}
