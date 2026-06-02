"""Application configuration loaded from environment variables."""

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    """Centralized application settings loaded from environment variables."""

    # Database
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER: str = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE: str = os.getenv("MYSQL_DATABASE", "yolo_detection")

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
        )

    @property
    def DATABASE_URL_SYNC(self) -> str:
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
        )

    # Redis
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production-32-chars-min")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRATION_HOURS: int = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))

    # Upload
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "uploads")
    MAX_IMAGE_SIZE_MB: int = int(os.getenv("MAX_IMAGE_SIZE_MB", "20"))
    MAX_VIDEO_SIZE_MB: int = int(os.getenv("MAX_VIDEO_SIZE_MB", "500"))
    MAX_MODEL_SIZE_MB: int = int(os.getenv("MAX_MODEL_SIZE_MB", "200"))

    @property
    def MAX_IMAGE_SIZE_BYTES(self) -> int:
        return self.MAX_IMAGE_SIZE_MB * 1024 * 1024

    @property
    def MAX_VIDEO_SIZE_BYTES(self) -> int:
        return self.MAX_VIDEO_SIZE_MB * 1024 * 1024

    @property
    def MAX_MODEL_SIZE_BYTES(self) -> int:
        return self.MAX_MODEL_SIZE_MB * 1024 * 1024

    # YOLO
    YOLO_DEFAULT_MODEL: str = os.getenv("YOLO_DEFAULT_MODEL", "yolov8n.pt")
    YOLO_CONFIDENCE_THRESHOLD: float = float(os.getenv("YOLO_CONFIDENCE_THRESHOLD", "0.25"))
    YOLO_DEVICE: str = os.getenv("YOLO_DEVICE", "auto")
    YOLO_MODELS_DIR: str = os.getenv("YOLO_MODELS_DIR", str(BASE_DIR / "models"))

    @property
    def yolo_models_dir(self) -> str:
        os.makedirs(self.YOLO_MODELS_DIR, exist_ok=True)
        return self.YOLO_MODELS_DIR

    # Temp files
    TEMP_DIR: str = os.getenv("TEMP_DIR", str(BASE_DIR / "temp"))

    @property
    def temp_dir(self) -> str:
        os.makedirs(self.TEMP_DIR, exist_ok=True)
        return self.TEMP_DIR

    # LLM
    LLM_TIMEOUT_SECONDS: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
    LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "2"))

    # Server
    BACKEND_HOST: str = os.getenv("BACKEND_HOST", "0.0.0.0")
    BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8000"))
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")


settings = Settings()
