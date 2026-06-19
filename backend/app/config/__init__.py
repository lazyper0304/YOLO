"""Application configuration — domain-specific settings composed via multiple inheritance."""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

from app.config.database import DatabaseSettings
from app.config.redis import RedisSettings
from app.config.auth import AuthSettings
from app.config.upload import UploadSettings
from app.config.yolo import YOLOSettings
from app.config.llm import LLMSettings
from app.config.server import ServerSettings
from app.config.rag import RAGSettings


class Settings(
    DatabaseSettings,
    RedisSettings,
    AuthSettings,
    UploadSettings,
    YOLOSettings,
    LLMSettings,
    ServerSettings,
    RAGSettings,
):
    """Composite settings — combines all domain configurations."""


settings = Settings()
