"""Unit tests for Pydantic schemas.

Covers: auth schemas (register/login validation), detection schemas
(mode enum), LLM config schemas, history schemas.
"""

import pytest
from pydantic import ValidationError

from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, UserResponse
from app.schemas.detection import (
    BBoxItem,
    LLMAnalysisResult,
    DetectionResult,
    ImageDetectionQuery,
)
from app.schemas.llm_config import (
    LLMConfigCreate,
    LLMConfigUpdate,
    LLMConfigResponse,
    LLMTestResponse,
)
from app.schemas.yolo_model import (
    YOLOModelCreate,
    YOLOModelUpdate,
    YOLOModelResponse,
)
from app.schemas.history import (
    HistoryListQuery,
    HistoryItemResponse,
    HistoryDetailResponse,
    PaginatedResponse,
)


# ======================================================================
# Auth schemas
# ======================================================================

class TestRegisterRequest:
    """Tests for RegisterRequest validation."""

    def test_valid_register(self):
        req = RegisterRequest(
            username="alice_2024",
            email="alice@example.com",
            password="secure123",
        )
        assert req.username == "alice_2024"
        assert req.email == "alice@example.com"

    def test_username_too_short(self):
        with pytest.raises(ValidationError):
            RegisterRequest(username="ab", email="a@b.com", password="123456")

    def test_username_too_long(self):
        with pytest.raises(ValidationError):
            RegisterRequest(
                username="a" * 51, email="a@b.com", password="123456"
            )

    def test_username_invalid_chars(self):
        """Username must match ^[a-zA-Z0-9_]+$ only."""
        invalid_names = [
            "user name",    # space
            "user-name",    # hyphen
            "user.name",    # dot
            "用户",          # Chinese
            "user@name",    # at sign
        ]
        for name in invalid_names:
            with pytest.raises(ValidationError):
                RegisterRequest(username=name, email="a@b.com", password="123456")

    def test_username_valid_chars(self):
        """Acceptable usernames."""
        valid = ["alice", "ALICE", "alice_123", "user_1", "A_B_C", "a" * 3]
        for name in valid:
            req = RegisterRequest(username=name, email="a@b.com", password="123456")
            assert req.username == name

    def test_password_too_short(self):
        with pytest.raises(ValidationError):
            RegisterRequest(
                username="alice", email="a@b.com", password="12345"
            )  # min 6

    def test_password_too_long(self):
        with pytest.raises(ValidationError):
            RegisterRequest(
                username="alice", email="a@b.com", password="a" * 101
            )  # max 100

    def test_invalid_email(self):
        invalid_emails = ["notanemail", "missing@domain", "@nouser.com", ""]
        for email in invalid_emails:
            with pytest.raises(ValidationError):
                RegisterRequest(username="alice", email=email, password="123456")

    def test_boundary_username_length(self):
        """Username exactly 3 and 50 chars should pass."""
        RegisterRequest(username="abc", email="a@b.com", password="123456")
        RegisterRequest(username="a" * 50, email="a@b.com", password="123456")

    def test_boundary_password_length(self):
        """Password exactly 6 and 100 chars should pass."""
        RegisterRequest(username="alice", email="a@b.com", password="123456")
        RegisterRequest(username="alice", email="a@b.com", password="a" * 100)


class TestLoginRequest:
    """Tests for LoginRequest validation."""

    def test_valid_login(self):
        req = LoginRequest(username="alice", password="secret")
        assert req.username == "alice"
        assert req.password == "secret"

    def test_empty_username(self):
        with pytest.raises(ValidationError):
            LoginRequest(username="", password="secret")

    def test_empty_password(self):
        with pytest.raises(ValidationError):
            LoginRequest(username="alice", password="")


class TestTokenResponse:
    """Tests for TokenResponse."""

    def test_default_token_type(self):
        resp = TokenResponse(access_token="jwt.token.here")
        assert resp.token_type == "bearer"

    def test_custom_token_type(self):
        resp = TokenResponse(access_token="abc", token_type="Bearer")
        assert resp.token_type == "Bearer"


class TestUserResponse:
    """Tests for UserResponse."""

    def test_valid_user_response(self):
        resp = UserResponse(
            id=1,
            username="alice",
            email="alice@example.com",
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-02T00:00:00",
        )
        assert resp.id == 1
        assert resp.username == "alice"


# ======================================================================
# Detection schemas
# ======================================================================

class TestBBoxItem:
    """Tests for BBoxItem."""

    def test_valid_bbox(self):
        bbox = BBoxItem(
            x1=10.5, y1=20.3, x2=100.0, y2=200.0,
            confidence=0.95, class_name="person", class_id=0,
        )
        assert bbox.confidence == 0.95

    def test_zero_coordinates(self):
        """BBox with origin at (0,0) is valid."""
        bbox = BBoxItem(
            x1=0.0, y1=0.0, x2=10.0, y2=10.0,
            confidence=0.5, class_name="cat", class_id=15,
        )
        assert bbox.x1 == 0.0

    def test_negative_coordinates_are_allowed(self):
        """Pydantic doesn't enforce coordinate bounds."""
        bbox = BBoxItem(
            x1=-5.0, y1=-10.0, x2=100.0, y2=200.0,
            confidence=0.8, class_name="dog", class_id=16,
        )
        assert bbox.x1 == -5.0


class TestImageDetectionQuery:
    """Tests for ImageDetectionQuery (mode enum validation)."""

    def test_valid_modes(self):
        for mode in ("yolo_only", "llm_only", "collaborative"):
            q = ImageDetectionQuery(mode=mode)
            assert q.mode == mode

    def test_invalid_mode(self):
        with pytest.raises(ValidationError):
            ImageDetectionQuery(mode="invalid_mode")

    def test_default_mode(self):
        q = ImageDetectionQuery()
        assert q.mode == "yolo_only"

    def test_optional_ids_default_none(self):
        q = ImageDetectionQuery(mode="collaborative")
        assert q.model_id is None
        assert q.llm_config_id is None

    def test_with_ids(self):
        q = ImageDetectionQuery(
            mode="collaborative", model_id=5, llm_config_id=10
        )
        assert q.model_id == 5
        assert q.llm_config_id == 10


class TestDetectionResult:
    """Tests for DetectionResult."""

    def test_default_values(self):
        result = DetectionResult(mode="yolo_only", source_type="image")
        assert result.bboxes == []
        assert result.llm_analysis is None
        assert result.annotated_image_base64 is None
        assert result.processing_time_ms == 0.0

    def test_full_result(self):
        result = DetectionResult(
            mode="collaborative",
            source_type="image",
            bboxes=[
                BBoxItem(x1=0, y1=0, x2=10, y2=10, confidence=0.9,
                         class_name="car", class_id=2),
            ],
            llm_analysis=LLMAnalysisResult(
                summary="test",
                objects_detected=["car"],
                detailed_analysis="A car is visible",
            ),
            annotated_image_base64="base64string",
            processing_time_ms=1234.5,
        )
        assert len(result.bboxes) == 1
        assert result.llm_analysis is not None
        assert result.llm_analysis.summary == "test"


# ======================================================================
# LLM Config schemas
# ======================================================================

class TestLLMConfigCreate:
    """Tests for LLMConfigCreate validation."""

    def test_valid_create(self):
        cfg = LLMConfigCreate(
            name="My OpenAI",
            api_base_url="https://api.openai.com/v1",
            api_key="sk-test123",
            model_name="gpt-4o",
        )
        assert cfg.provider == "generic"  # default
        assert cfg.is_active is False

    def test_valid_providers(self):
        for provider in ("openai", "claude", "generic"):
            cfg = LLMConfigCreate(
                name="test",
                api_base_url="https://api.example.com",
                api_key="sk-123",
                model_name="test-model",
                provider=provider,
            )
            assert cfg.provider == provider

    def test_invalid_provider(self):
        with pytest.raises(ValidationError):
            LLMConfigCreate(
                name="test",
                api_base_url="https://api.example.com",
                api_key="sk-123",
                model_name="test",
                provider="invalid_provider",
            )

    def test_name_too_short(self):
        with pytest.raises(ValidationError):
            LLMConfigCreate(
                name="",
                api_base_url="https://api.example.com",
                api_key="sk-123",
                model_name="test",
            )

    def test_explicit_is_active(self):
        cfg = LLMConfigCreate(
            name="Active Config",
            api_base_url="https://api.example.com",
            api_key="sk-123",
            model_name="test",
            is_active=True,
        )
        assert cfg.is_active is True


class TestLLMConfigUpdate:
    """Tests for LLMConfigUpdate (all fields optional)."""

    def test_empty_update(self):
        """All fields None is valid."""
        cfg = LLMConfigUpdate()
        assert cfg.name is None
        assert cfg.api_key is None

    def test_partial_update(self):
        cfg = LLMConfigUpdate(name="New Name")
        assert cfg.name == "New Name"
        assert cfg.api_base_url is None

    def test_invalid_provider_in_update(self):
        with pytest.raises(ValidationError):
            LLMConfigUpdate(provider="bad_provider")

    def test_api_key_can_be_empty_string(self):
        """Note: current schema allows empty api_key on update (P2)."""
        cfg = LLMConfigUpdate(api_key="")
        assert cfg.api_key == ""


class TestLLMTestResponse:
    """Tests for LLMTestResponse."""

    def test_success_response(self):
        resp = LLMTestResponse(
            success=True,
            message="Connection successful",
            response_time_ms=245.67,
        )
        assert resp.success is True
        assert resp.response_time_ms == 245.67

    def test_failure_response(self):
        resp = LLMTestResponse(
            success=False,
            message="Timeout",
            response_time_ms=15000.0,
        )
        assert resp.success is False


# ======================================================================
# YOLO Model schemas
# ======================================================================

class TestYOLOModelCreate:
    """Tests for YOLOModelCreate."""

    def test_valid_create(self):
        m = YOLOModelCreate(name="my-model")
        assert m.name == "my-model"
        assert m.is_active is False

    def test_name_too_short(self):
        with pytest.raises(ValidationError):
            YOLOModelCreate(name="")


class TestYOLOModelUpdate:
    """Tests for YOLOModelUpdate."""

    def test_empty_update(self):
        m = YOLOModelUpdate()
        assert m.name is None
        assert m.is_active is None


# ======================================================================
# History schemas
# ======================================================================

class TestHistoryListQuery:
    """Tests for HistoryListQuery."""

    def test_defaults(self):
        q = HistoryListQuery()
        assert q.page == 1
        assert q.page_size == 20
        assert q.mode is None

    def test_custom_pagination(self):
        q = HistoryListQuery(page=3, page_size=50)
        assert q.page == 3
        assert q.page_size == 50

    def test_mode_filter(self):
        q = HistoryListQuery(mode="yolo_only")
        assert q.mode == "yolo_only"


class TestPaginatedResponse:
    """Tests for PaginatedResponse."""

    def test_valid(self):
        resp = PaginatedResponse(total=100, page=1, page_size=20, items=[])
        assert resp.total == 100
        assert resp.items == []
