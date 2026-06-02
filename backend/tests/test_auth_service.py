"""Unit tests for AuthService business logic.

Uses mock AsyncSession to test registration and login flows without a
real database.  conftest.py ensures the DB engine is mocked.

NOTE: hash_password / verify_password are mocked to avoid passlib/bcrypt
version incompatibility in the test environment.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.auth_service import AuthService
from app.models.user import User
from app.core.security import decode_access_token
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_security_settings() -> SimpleNamespace:
    """Return mock settings for token generation in login tests."""
    return SimpleNamespace(
        SECRET_KEY="test-secret-key-for-unit-tests-32c",
        JWT_ALGORITHM="HS256",
        JWT_EXPIRATION_HOURS=24,
    )


# A valid bcrypt-like hash for testing (not from actual bcrypt)
_FAKE_HASH = "$2b$12$LJ3m4ys3GZfnYMz8kVsKaOm3n7BXuDCVnZqKS9XJoklBRkGqK9XWa"


def make_user(id: int = 1, username: str = "alice", email: str = "alice@example.com",
              password_hash: str | None = None) -> User:
    """Create a User instance for testing."""
    return User(
        id=id,
        username=username,
        email=email,
        password_hash=password_hash or _FAKE_HASH,
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class TestRegistration:
    """Tests for AuthService.register."""

    @pytest.fixture(autouse=True)
    def _patch_hash(self):
        """Mock hash_password to avoid passlib/bcrypt incompatibility."""
        with patch("app.services.auth_service.hash_password",
                   return_value=_FAKE_HASH):
            yield

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_successful_registration(self, mock_db):
        """Registering with a unique username and email succeeds."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = AuthService(mock_db)
        user = await service.register(
            username="newuser", email="new@example.com", password="secure123"
        )

        assert user.username == "newuser"
        assert user.email == "new@example.com"
        assert user.password_hash != "secure123"
        assert user.password_hash.startswith("$2")
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_username_already_exists(self, mock_db):
        """Registration fails when the username is taken."""
        existing_user = make_user()
        call_results = [existing_user, None]

        async def side_effect(stmt):
            m = MagicMock()
            val = call_results.pop(0) if call_results else None
            m.scalar_one_or_none.return_value = val
            return m

        mock_db.execute = AsyncMock(side_effect=side_effect)

        service = AuthService(mock_db)
        with pytest.raises(HTTPException) as exc_info:
            await service.register("alice", "new@example.com", "secure123")
        assert exc_info.value.status_code == 422
        assert "Username already exists" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_email_already_exists(self, mock_db):
        """Registration fails when the email is taken."""
        existing_user = make_user()
        call_results = [None, existing_user]

        async def side_effect(stmt):
            m = MagicMock()
            val = call_results.pop(0) if call_results else None
            m.scalar_one_or_none.return_value = val
            return m

        mock_db.execute = AsyncMock(side_effect=side_effect)

        service = AuthService(mock_db)
        with pytest.raises(HTTPException) as exc_info:
            await service.register("newuser", "alice@example.com", "secure123")
        assert exc_info.value.status_code == 422
        assert "Email already exists" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class TestLogin:
    """Tests for AuthService.login."""

    @pytest.fixture(autouse=True)
    def _patch_verify(self):
        """Mock verify_password to avoid passlib/bcrypt incompatibility."""
        with patch("app.services.auth_service.verify_password",
                   side_effect=lambda plain, hashed: plain == "correct_password" or
                   plain == "pass" or plain == "mypassword" or plain == "right"):
            yield

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_successful_login(self, mock_db):
        """Login with valid credentials returns a JWT token string."""
        user = make_user()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = mock_result

        with patch("app.core.security.settings", _mock_security_settings()):
            service = AuthService(mock_db)
            token = await service.login("alice", "correct_password")

        assert isinstance(token, str)
        assert len(token) > 20
        # Verify token can be decoded (sub is now str, P0-1 fixed)
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == str(user.id)
        assert payload["username"] == "alice"

    @pytest.mark.asyncio
    async def test_wrong_password(self, mock_db):
        """Login with wrong password raises 401."""
        user = make_user()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = mock_result

        with patch("app.core.security.settings", _mock_security_settings()):
            service = AuthService(mock_db)
            with pytest.raises(HTTPException) as exc_info:
                await service.login("alice", "wrong")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_user_not_found(self, mock_db):
        """Login with non-existent username raises 401."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with patch("app.core.security.settings", _mock_security_settings()):
            service = AuthService(mock_db)
            with pytest.raises(HTTPException) as exc_info:
                await service.login("ghost", "anything")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_login_token_contains_username(self, mock_db):
        """The returned JWT contains the username in the payload."""
        user = make_user(username="bob")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = mock_result

        with patch("app.core.security.settings", _mock_security_settings()):
            service = AuthService(mock_db)
            token = await service.login("bob", "pass")

        assert isinstance(token, str)
        assert len(token) > 20
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["username"] == "bob"


# ---------------------------------------------------------------------------
# Integration: register then login
# ---------------------------------------------------------------------------

class TestRegisterThenLogin:
    """End-to-end test of register → login flow using mocked DB."""

    @pytest.mark.asyncio
    async def test_register_then_login(self):
        """A newly registered user can log in with their password."""
        with patch("app.services.auth_service.hash_password",
                   return_value=_FAKE_HASH), \
             patch("app.services.auth_service.verify_password",
                   side_effect=lambda plain, hashed: plain == "mypassword"):
            db = AsyncMock(spec=AsyncSession)
            reg_results = [None, None]

            async def reg_side_effect(stmt):
                m = MagicMock()
                m.scalar_one_or_none.return_value = reg_results.pop(0) if reg_results else None
                return m

            db.execute = AsyncMock(side_effect=reg_side_effect)
            db.add = MagicMock()
            db.flush = AsyncMock()

            async def refresh_side_effect(user):
                user.id = 42
            db.refresh = AsyncMock(side_effect=refresh_side_effect)

            service = AuthService(db)
            user = await service.register("newuser", "new@test.com", "mypassword")
            assert user.id == 42

            db.execute = AsyncMock()
            login_result = MagicMock()
            login_result.scalar_one_or_none.return_value = user
            db.execute.return_value = login_result

            with patch("app.core.security.settings", _mock_security_settings()):
                token = await service.login("newuser", "mypassword")
            assert token is not None
            assert isinstance(token, str)
