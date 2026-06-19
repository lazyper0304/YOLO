"""Authentication and JWT configuration."""
import os


class AuthSettings:
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production-32-chars-min")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRATION_HOURS: int = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))
