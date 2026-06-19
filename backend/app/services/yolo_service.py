"""YOLO service: model loading, inference, LRU caching.

Optimized with:
- ProcessPoolExecutor for CPU-intensive inference
- Configurable model caching
- Thread-safe model loading
"""

import asyncio
import logging
import os
import threading
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import torch
import ultralytics.nn.tasks as ultralytics_tasks

logger = logging.getLogger(__name__)

# PyTorch 2.6+ 兼容：torch.load 默认 weights_only=True，YOLO 模型加载需要 weights_only=False
# 同时处理旧版本模型文件引用已移除的 ultralytics.yolo 子模块
def _setup_yolo_compat():
    import sys

    # 为旧模型创建 ultralytics.yolo.* 虚拟模块别名
    _yolo_aliases = {
        "ultralytics.yolo": "ultralytics.models.yolo",
        "ultralytics.yolo.utils": "ultralytics.utils",
        "ultralytics.yolo.engine": "ultralytics.engine",
        "ultralytics.yolo.data": "ultralytics.data",
    }
    for old_name, new_name in _yolo_aliases.items():
        if old_name not in sys.modules:
            try:
                import importlib
                new_mod = importlib.import_module(new_name)
                sys.modules[old_name] = new_mod
            except ImportError:
                pass

    # Patch torch_safe_load to use weights_only=False
    def _patched_torch_safe_load(weight: str):
        ckpt = torch.load(weight, map_location="cpu", weights_only=False)
        return ckpt, weight

    ultralytics_tasks.torch_safe_load = _patched_torch_safe_load


_setup_yolo_compat()

# ultralytics 8.2+ 兼容：C3k2 已在 block.py 中移除，映射到 C2f
import ultralytics.nn.modules.block as _block
if not hasattr(_block, "C3k2"):
    from ultralytics.nn.modules.block import C2f
    _block.C3k2 = C2f

from app.config import settings


def _run_yolo_inference(model_path: str, image_path: str, conf: float, device: str) -> list:
    """Run YOLO inference in a separate process.

    This function is designed to be called via ProcessPoolExecutor.
    It loads the model and runs inference in isolation to avoid GIL contention.

    Returns:
        List of raw detection results (boxes, confidences, class_ids, class_names)
    """
    from ultralytics import YOLO

    model = YOLO(model_path)
    model.to(device)
    results = model(image_path, conf=conf)

    detections = []
    for result in results:
        if result.boxes is not None:
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf_val = float(box.conf[0])
                cls_id = int(box.cls[0])
                cls_name = model.names.get(cls_id, f"class_{cls_id}") if hasattr(model, "names") else f"class_{cls_id}"
                detections.append({
                    "x1": round(x1, 2),
                    "y1": round(y1, 2),
                    "x2": round(x2, 2),
                    "y2": round(y2, 2),
                    "confidence": round(conf_val, 4),
                    "class_name": cls_name,
                    "class_id": cls_id,
                })

    # Sort by confidence descending
    detections.sort(key=lambda b: b["confidence"], reverse=True)
    return detections


class YOLOService:
    """Singleton YOLO service with lazy loading, LRU caching, and process-based inference.

    Uses ProcessPoolExecutor for CPU-intensive inference tasks to bypass GIL limitations.
    Model loading remains in thread pool as it's I/O bound (reading weights from disk).
    """

    _instance: "YOLOService | None" = None
    _lock = threading.Lock()

    # Model registry — dynamically populated from uploaded models
    MODEL_REGISTRY: dict[str, str] = {}

    def __new__(cls) -> "YOLOService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    # Initialize all attributes here to avoid AttributeError
                    inst._models = {}
                    inst._access_order = []
                    inst._max_cached = 2
                    inst._model_lock = asyncio.Lock()
                    inst._inference_locks = {}
                    inst._process_executor = ProcessPoolExecutor(
                        max_workers=settings.PROCESS_POOL_MAX_WORKERS,
                    )
                    inst._setup_done = False
                    cls._instance = inst
                    logger.info("YOLOService created (process_pool_workers=%d)", settings.PROCESS_POOL_MAX_WORKERS)
        return cls._instance

    def __init__(self):
        if self._setup_done:
            return
        self._setup_done = True

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

        logger.info("YOLOService initialized")

    @property
    def process_executor(self) -> ProcessPoolExecutor:
        """Expose process executor for direct use if needed."""
        return self._process_executor

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
        """Load a YOLO model with LRU caching (max 2 resident).

        Model loading is done in thread pool as it's primarily I/O bound.
        """
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
                    logger.info("Evicting model from cache: %s", evict_path)
                    del self._models[evict_path]

            # Load the model (run in thread to avoid blocking event loop)
            from ultralytics import YOLO

            device = settings.YOLO_DEVICE
            if device == "auto":
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"

            loop = asyncio.get_event_loop()
            try:
                # Model loading is I/O bound, use thread pool
                model = await loop.run_in_executor(
                    None, lambda: YOLO(model_path)
                )
            except Exception as e:
                raise RuntimeError(f"模型加载失败，ultralytics版本可能不兼容: {str(e)[:300]}") from e

            # Set device
            model.to(device)

            self._models[model_path] = model
            self._access_order.append(model_path)
            logger.info("Loaded model: %s (device=%s, cached=%d)", model_path, device, len(self._models))
            return model

    async def detect(
        self,
        image_path: str,
        model_path: str | None = None,
        confidence_threshold: float | None = None,
        use_process_pool: bool = True,
    ) -> list[dict]:
        """Run YOLO detection on an image and return bbox results.

        Uses a per-model inference lock so that multiple tasks using the same
        model are serialized (GPU memory safety), while tasks using different
        models can run in parallel.

        Args:
            image_path: Path to the image file
            model_path: Path to the YOLO model weights
            confidence_threshold: Detection confidence threshold
            use_process_pool: If True, run inference in ProcessPoolExecutor (recommended for CPU-bound work)
                             If False, run in thread pool (may be better for GPU-bound work with CUDA)
        """
        if model_path is None:
            raise ValueError("未选择YOLO模型，请上传并选择模型后进行检测")

        conf = confidence_threshold if confidence_threshold is not None else settings.YOLO_CONFIDENCE_THRESHOLD

        # Determine device
        device = settings.YOLO_DEVICE
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"

        if use_process_pool and device == "cpu":
            # CPU-bound: use process pool to bypass GIL
            return await self._detect_with_process_pool(image_path, model_path, conf, device)
        else:
            # GPU-bound or fallback: use model in memory with thread pool
            return await self._detect_with_model(image_path, model_path, conf)

    async def _detect_with_process_pool(
        self,
        image_path: str,
        model_path: str,
        conf: float,
        device: str,
    ) -> list[dict]:
        """Run detection in a separate process (best for CPU-bound inference)."""
        # Acquire per-model inference lock to serialize same-model concurrency
        if model_path not in self._inference_locks:
            self._inference_locks[model_path] = asyncio.Lock()

        async with self._inference_locks[model_path]:
            loop = asyncio.get_event_loop()
            try:
                bboxes = await loop.run_in_executor(
                    self._process_executor,
                    _run_yolo_inference, model_path, image_path, conf, device,
                )
                return bboxes
            except Exception as e:
                logger.error("YOLO inference failed: %s", str(e))
                raise

    async def _detect_with_model(
        self,
        image_path: str,
        model_path: str,
        conf: float,
    ) -> list[dict]:
        """Run detection using in-memory model (best for GPU-bound inference with CUDA)."""
        model = await self.load_model(model_path)

        # Acquire per-model inference lock to serialize same-model concurrency
        if model_path not in self._inference_locks:
            self._inference_locks[model_path] = asyncio.Lock()

        async with self._inference_locks[model_path]:
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

    async def cleanup(self):
        """Cleanup resources on shutdown."""
        logger.info("Cleaning up YOLOService...")
        self._models.clear()
        self._access_order.clear()
        self._inference_locks.clear()
        # Note: ProcessPoolExecutor is shutdown by TaskQueue
        logger.info("YOLOService cleanup complete")
