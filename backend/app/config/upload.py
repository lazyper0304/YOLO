"""Upload size limits and directories."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class UploadSettings:
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
