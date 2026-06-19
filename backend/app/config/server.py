"""Server runtime configuration."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class ServerSettings:
    BACKEND_HOST: str = os.getenv("BACKEND_HOST", "0.0.0.0")
    BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8000"))
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    TEMP_DIR: str = os.getenv("TEMP_DIR", str(BASE_DIR / "temp"))

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def temp_dir(self) -> str:
        os.makedirs(self.TEMP_DIR, exist_ok=True)
        return self.TEMP_DIR
