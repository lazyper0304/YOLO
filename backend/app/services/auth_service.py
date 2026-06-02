"""Authentication service: register, login, token generation."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password, create_access_token
from app.models.user import User


class AuthService:
    """Handles user registration, login, and JWT token generation."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, username: str, email: str, password: str) -> User:
        """Register a new user with unique username and email checks."""
        # Check username uniqueness
        existing_user = await self.db.execute(
            select(User).where(User.username == username)
        )
        if existing_user.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Username already exists",
            )

        # Check email uniqueness
        existing_email = await self.db.execute(
            select(User).where(User.email == email)
        )
        if existing_email.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Email already exists",
            )

        user = User(
            username=username,
            email=email,
            password_hash=hash_password(password),
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def login(self, username: str, password: str) -> str:
        """Authenticate user and return a JWT access token."""
        result = await self.db.execute(
            select(User).where(User.username == username)
        )
        user = result.scalar_one_or_none()

        if user is None or not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        return create_access_token(data={"sub": str(user.id), "username": user.username})
