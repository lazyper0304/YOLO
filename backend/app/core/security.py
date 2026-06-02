"""Security utilities: JWT tokens, password hashing, API key encryption."""

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt, JWTError
from passlib.context import CryptContext
from cryptography.fernet import Fernet
import base64
import hashlib

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Derive a Fernet-compatible key from SECRET_KEY (must be 32 url-safe base64 bytes)
_fernet_key = base64.urlsafe_b64encode(
    hashlib.sha256(settings.SECRET_KEY.encode()).digest()
)
_cipher = Fernet(_fernet_key)


def hash_password(password: str) -> str:
    """Hash a plain-text password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against its bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token with expiration."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(hours=settings.JWT_EXPIRATION_HOURS)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode and validate a JWT access token. Returns payload or None."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


def encrypt_api_key(api_key: str) -> str:
    """Encrypt an API key using AES-256-CBC (Fernet)."""
    return _cipher.encrypt(api_key.encode()).decode()


def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt an encrypted API key."""
    return _cipher.decrypt(encrypted_key.encode()).decode()
