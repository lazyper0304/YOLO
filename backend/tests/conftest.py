"""pytest configuration: ensures backend imports work without MySQL/Redis."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------
# Mock settings with harmless database URLs before any imports
# ---------------------------------------------------------------
_mock_settings = SimpleNamespace(
    DATABASE_URL="sqlite+aiosqlite:///:memory:",
    DATABASE_URL_SYNC="sqlite:///:memory:",
    ENVIRONMENT="test",
    SECRET_KEY="test-secret-key-for-unit-tests-32c",
    JWT_ALGORITHM="HS256",
    JWT_EXPIRATION_HOURS=24,
    UPLOAD_DIR="/tmp/yolo-test-uploads",
    MAX_IMAGE_SIZE_MB=20,
    YOLO_DEFAULT_MODEL="yolov8n.pt",
    YOLO_CONFIDENCE_THRESHOLD=0.25,
    YOLO_DEVICE="cpu",
    LLM_TIMEOUT_SECONDS=60,
    LLM_MAX_RETRIES=2,
    CORS_ORIGINS="http://localhost:5173",
    cors_origins_list=["http://localhost:5173"],
)

# Replace settings at module level
import app.config
app.config.settings = _mock_settings

# Create a fake async engine
_fake_engine = MagicMock(name="fake_async_engine")

# Patch sqlalchemy's create_async_engine to return the fake
import sqlalchemy.ext.asyncio as _sa
_sa.create_async_engine = MagicMock(return_value=_fake_engine)
_sa.async_sessionmaker = MagicMock()
