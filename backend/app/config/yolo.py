"""YOLO model configuration."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class YOLOSettings:
    YOLO_DEFAULT_MODEL: str = os.getenv("YOLO_DEFAULT_MODEL", "yolo26n.pt")
    YOLO_CONFIDENCE_THRESHOLD: float = float(os.getenv("YOLO_CONFIDENCE_THRESHOLD", "0.25"))
    YOLO_DEVICE: str = os.getenv("YOLO_DEVICE", "auto")
    YOLO_MODELS_DIR: str = os.getenv("YOLO_MODELS_DIR", str(BASE_DIR / "models"))

    # Task queue concurrency settings
    TASK_MAX_WORKERS: int = int(os.getenv("TASK_MAX_WORKERS", "3"))
    TASK_TIMEOUT_SECONDS: int | None = None

    # Process/Thread pool settings
    PROCESS_POOL_MAX_WORKERS: int = int(os.getenv("PROCESS_POOL_MAX_WORKERS", "2"))
    THREAD_POOL_MAX_WORKERS: int = int(os.getenv("THREAD_POOL_MAX_WORKERS", "4"))

    @property
    def yolo_models_dir(self) -> str:
        os.makedirs(self.YOLO_MODELS_DIR, exist_ok=True)
        return self.YOLO_MODELS_DIR
