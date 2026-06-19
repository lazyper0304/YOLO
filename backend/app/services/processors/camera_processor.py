"""Camera task processors — IP camera and webcam."""
import os
import cv2
import asyncio
import tempfile
import logging
from typing import Callable
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.detection_record import DetectionRecord
from app.models.yolo_model import YOLOModel
from app.models.llm_config import LLMConfig
from app.core.security import decrypt_api_key
from app.config import settings

logger = logging.getLogger(__name__)


class CameraIPProcessor:
    """IP camera backend processing with optional YOLO/LLM analysis."""

    def __init__(self, db: AsyncSession, running_check: Callable[[], bool]):
        self.db = db
        self._running = running_check

    async def process(self, record: DetectionRecord) -> None:
        from app.services.yolo_service import YOLOService

        yolo = YOLOService()
        model_path = None
        if record.yolo_model_id:
            r = await self.db.execute(
                select(YOLOModel).where(YOLOModel.id == record.yolo_model_id)
            )
            m = r.scalar_one_or_none()
            if m:
                model_path = m.file_path

        cap = cv2.VideoCapture(record.source_path)
        if not cap.isOpened():
            record.result_json = {"error": f"无法打开摄像头: {record.source_path}"}
            record.status = "failed"
            return

        all_detections: dict[str, int] = {}
        frame_count = 0
        detected_count = 0
        interval = record.frame_interval_seconds or 5
        frames_per_interval = max(1, int(5 * interval))
        frames: list[dict] = []
        frame_idx = 0

        record.status = "camera_running"
        await self.db.commit()

        try:
            while self._running():
                ret, frame = cap.read()
                if not ret:
                    await asyncio.sleep(1)
                    continue
                if frame_count % frames_per_interval == 0:
                    try:
                        tmp = tempfile.NamedTemporaryFile(
                            suffix=".jpg", delete=False, dir=settings.temp_dir
                        )
                        cv2.imwrite(tmp.name, frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                        tmp.close()

                        frame_result: dict = {
                            "frame_index": frame_idx,
                            "time_seconds": frame_idx * interval,
                            "bboxes": [],
                        }
                        frame_idx += 1

                        # YOLO
                        if record.mode in ("yolo_only", "collaborative"):
                            bboxes = await yolo.detect(tmp.name, model_path=model_path)
                            frame_result["bboxes"] = bboxes
                            for b in bboxes:
                                cls = b["class_name"]
                                all_detections[cls] = all_detections.get(cls, 0) + 1
                                detected_count += 1

                        # LLM
                        if record.mode in ("llm_only", "collaborative"):
                            try:
                                from app.services.llm_service import LLMService
                                from app.services.image_service import ImageService

                                img_svc = ImageService()
                                llm_svc = LLMService()

                                llm_config = None
                                if record.llm_config_id:
                                    r = await self.db.execute(
                                        select(LLMConfig).where(
                                            LLMConfig.id == record.llm_config_id,
                                            LLMConfig.user_id == record.user_id,
                                        )
                                    )
                                    llm_config = r.scalar_one_or_none()
                                if llm_config is None:
                                    r = await self.db.execute(
                                        select(LLMConfig).where(
                                            LLMConfig.user_id == record.user_id,
                                            LLMConfig.is_active == True,
                                        )
                                    )
                                    llm_config = r.scalar_one_or_none()

                                if llm_config:
                                    api_key = decrypt_api_key(llm_config.api_key)
                                    is_region = record.mode == "collaborative" and getattr(record, "llm_analysis_scope", "full") == "region"

                                    if not is_region:
                                        # Full-frame LLM analysis
                                        prompt = record.analysis_prompt or None
                                        if prompt:
                                            prompt = (
                                                f"摄像头实时画面分析（第{frame_result['frame_index']}帧，"
                                                f"时间{frame_result['time_seconds']}秒）。\n"
                                                f"分析主题：{prompt}\n\n"
                                                f"请观察该帧画面并描述你看到的内容。"
                                                f"以JSON格式返回：{{\"summary\":\"...\", \"objects_detected\":[...], \"detailed_analysis\":\"...\"}}"
                                            )
                                        llm_result = await llm_svc.analyze_image(
                                            api_base_url=llm_config.api_base_url,
                                            api_key=api_key,
                                            model_name=llm_config.model_name,
                                            image_base64=img_svc.encode_image_base64(tmp.name),
                                            prompt=prompt,
                                            provider=llm_config.provider,
                                        )
                                        frame_result["llm_analysis"] = llm_result
                                    else:
                                        # Region-only mode: analyze each YOLO-detected region
                                        region_analyses = []
                                        for bbox in frame_result.get("bboxes", []):
                                            region_b64 = await img_svc.crop_region_base64(
                                                tmp.name, x1=bbox["x1"], y1=bbox["y1"], x2=bbox["x2"], y2=bbox["y2"])
                                            region_result = await llm_svc.analyze_region(
                                                api_base_url=llm_config.api_base_url,
                                                api_key=api_key,
                                                model_name=llm_config.model_name,
                                                region_base64=region_b64,
                                                region_label=bbox["class_name"],
                                                provider=llm_config.provider,
                                            )
                                            region_analyses.append(region_result)
                                        frame_result["llm_analysis"] = {
                                            "analysis_scope": "region",
                                            "region_analyses": region_analyses,
                                        }
                            except Exception as e:
                                frame_result["llm_analysis"] = {"error": str(e)}

                        frames.append(frame_result)
                        os.unlink(tmp.name)

                        # Periodic save
                        if len(frames) % 3 == 0:
                            summary = sorted(
                                [{"class": k, "count": v} for k, v in all_detections.items()],
                                key=lambda x: -x["count"],
                            )
                            record.result_json = {
                                "source_type": "camera",
                                "camera_url": record.source_path,
                                "frame_count": len(frames),
                                "total_objects": detected_count,
                                "frames": frames,
                                "detection_summary": summary,
                                "analysis_prompt": record.analysis_prompt,
                            }
                            await self.db.commit()

                    except Exception as e:
                        logger.warning(f"Camera frame error: {e}")
                frame_count += 1
                await asyncio.sleep(0.01)
        finally:
            cap.release()
            summary = sorted(
                [{"class": k, "count": v} for k, v in all_detections.items()],
                key=lambda x: -x["count"],
            )
            record.result_json = {
                "source_type": "camera",
                "camera_url": record.source_path,
                "frame_count": len(frames),
                "total_objects": detected_count,
                "frames": frames,
                "detection_summary": summary,
                "analysis_prompt": record.analysis_prompt,
            }
            record.status = "completed"
            record.progress = 100
            await self.db.commit()


class CameraWebcamProcessor:
    """Webcam backend placeholder — real work done by frontend via /analyze-frame."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def process(self, record: DetectionRecord) -> None:
        """Mark webcam task as camera_running for frontend-driven processing."""
        record.status = "camera_running"
        record.result_json = {
            "source_type": "camera",
            "note": "webcam detection handled by frontend",
            "frames": [],
        }
        await self.db.commit()
