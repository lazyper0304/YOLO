"""YOLO service: model loading, inference, LRU caching."""

import asyncio
import os
import threading
from pathlib import Path
from typing import Any

import torch
import ultralytics.nn.tasks as ultralytics_tasks

# PyTorch 2.6+ 兼容：patch torch_safe_load 使用 weights_only=False
_original_torch_safe_load = ultralytics_tasks.torch_safe_load


def _patched_torch_safe_load(weight: str):
    """Patch to allow loading ultralytics model checkpoints with PyTorch 2.6+."""
    ckpt = torch.load(weight, map_location="cpu", weights_only=False)
    return ckpt, weight


ultralytics_tasks.torch_safe_load = _patched_torch_safe_load

from app.config import settings


class YOLOService:
    """Singleton YOLO service with lazy loading and LRU caching (max 2 models)."""

    _instance: "YOLOService | None" = None
    _lock = threading.Lock()

    # Model registry — dynamically populated from uploaded models
    MODEL_REGISTRY: dict[str, str] = {}

    def __new__(cls) -> "YOLOService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._models: dict[str, Any] = {}  # model_path -> YOLO model object
        self._access_order: list[str] = []  # LRU tracking
        self._max_cached = 2
        self._model_lock = asyncio.Lock()

        # Set ultralytics to use project-local directories
        os.environ.setdefault("ULTRALYTICS_CONFIG_DIR", str(settings.yolo_models_dir))
        os.environ.setdefault("YOLO_CONFIG_DIR", str(settings.yolo_models_dir))
        try:
            from ultralytics.utils import SETTINGS
            SETTINGS.update({
                "datasets_dir": str(settings.yolo_models_dir),
                "weights_dir": str(settings.yolo_models_dir),
                "runs_dir": str(settings.yolo_models_dir),
            })
        except Exception:
            pass

    async def pre_download_models(self):
        """Pre-download lightweight default models in the background (non-blocking)."""
        from ultralytics import YOLO

        async def _download(model_name: str):
            try:
                if not os.path.exists(model_name):
                    model = YOLO(model_name)
                    del model
            except Exception:
                pass  # Silently skip download failures

        tasks = [_download(m) for m in self._startup_models]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def load_model(self, model_path: str) -> Any:
        """Load a YOLO model with LRU caching (max 2 resident)."""
        async with self._model_lock:
            # Check if already loaded
            if model_path in self._models:
                # Move to end of access order (most recent)
                self._access_order.remove(model_path)
                self._access_order.append(model_path)
                return self._models[model_path]

            # Evict least recently used if cache is full
            while len(self._models) >= self._max_cached and self._access_order:
                evict_path = self._access_order.pop(0)
                if evict_path in self._models:
                    del self._models[evict_path]

            # Load the model (run in thread to avoid blocking)
            from ultralytics import YOLO

            device = settings.YOLO_DEVICE
            if device == "auto":
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"

            loop = asyncio.get_event_loop()
            model = await loop.run_in_executor(
                None, lambda: YOLO(model_path)
            )
            # Set device
            model.to(device)

            self._models[model_path] = model
            self._access_order.append(model_path)
            return model

    async def detect(
        self,
        image_path: str,
        model_path: str | None = None,
        confidence_threshold: float | None = None,
    ) -> list[dict]:
        """Run YOLO detection on an image and return bbox results."""
        if model_path is None:
            raise ValueError("未选择YOLO模型，请上传并选择模型后进行检测")

        conf = confidence_threshold if confidence_threshold is not None else settings.YOLO_CONFIDENCE_THRESHOLD

        model = await self.load_model(model_path)
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None, lambda: model(image_path, conf=conf)
        )

        bboxes = []
        for result in results:
            if result.boxes is not None:
                for box in result.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    conf_val = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    cls_name = model.names.get(cls_id, f"class_{cls_id}") if hasattr(model, "names") else f"class_{cls_id}"
                    bboxes.append({
                        "x1": round(x1, 2),
                        "y1": round(y1, 2),
                        "x2": round(x2, 2),
                        "y2": round(y2, 2),
                        "confidence": round(conf_val, 4),
                        "class_name": cls_name,
                        "class_id": cls_id,
                    })

        # Sort by confidence descending
        bboxes.sort(key=lambda b: b["confidence"], reverse=True)
        return bboxes

    async def get_available_models(self) -> list[dict]:
        """Return all registered YOLO models, marked as downloaded or not."""
        models = []
        for key, path in self.MODEL_REGISTRY.items():
            downloaded = os.path.exists(path)
            models.append({
                "key": key,
                "name": path,
                "is_builtin": True,
                "downloaded": downloaded,
            })
        # Sort: default first, then by version, then by size
        models.sort(key=lambda m: (
            0 if m["key"] == "default" else 1,
            m["name"],
        ))
        return models

    async def get_model_classes(self, model_path: str) -> list[str]:
        """Return the class names a YOLO model can detect (lazy-loads model)."""
        try:
            model = await self.load_model(model_path)
            if hasattr(model, "names"):
                return list(model.names.values())
        except Exception:
            pass
        return []
