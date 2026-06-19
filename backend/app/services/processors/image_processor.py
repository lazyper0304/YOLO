"""Image processor — single image YOLO/LLM detection."""
import os
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.detection_record import DetectionRecord

logger = logging.getLogger(__name__)


class ImageProcessor:
    """Process a single image through YOLO + optional LLM."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def process(self, record: DetectionRecord) -> None:
        from app.services.detection_service import DetectionService

        service = DetectionService(self.db)
        with open(record.source_path, "rb") as f:
            image_content = f.read()
        result = await service.process_image_detection(
            user_id=record.user_id,
            image_content=image_content,
            original_filename=os.path.basename(record.source_path),
            mode=record.mode,
            model_id=record.yolo_model_id,
            llm_config_id=record.llm_config_id,
            save_record=False,
            llm_analysis_scope=getattr(record, "llm_analysis_scope", "full"),
            analysis_prompt=getattr(record, "analysis_prompt", None),
        )
        record.result_json = {
            "mode": result["mode"],
            "bboxes": result["bboxes"],
            "llm_analysis": result["llm_analysis"],
        }
        record.status = "completed"
        record.progress = 100
        record.thumbnail_path = result.get("thumbnail_path")
