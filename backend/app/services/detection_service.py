"""Detection service: orchestrates YOLO + LLM detection workflows."""

import asyncio
import os
import time
import base64
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import decrypt_api_key
from app.models.detection_record import DetectionRecord
from app.models.llm_config import LLMConfig
from app.models.yolo_model import YOLOModel
from app.services.yolo_service import YOLOService
from app.services.llm_service import LLMService
from app.services.image_service import ImageService
from app.utils.file_utils import save_upload_file


class DetectionService:
    """Orchestrates the full detection pipeline: YOLO only, LLM only, or collaborative."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.yolo_service = YOLOService()
        self.llm_service = LLMService()
        self.image_service = ImageService()

    async def process_image_detection(
        self,
        user_id: int,
        image_content: bytes,
        original_filename: str,
        mode: str,
        model_id: int | None = None,
        llm_config_id: int | None = None,
        save_record: bool = True,
    ) -> dict:
        """Run the full image detection pipeline and persist results."""
        start_time = time.time()

        # Save the uploaded image
        image_path = await save_upload_file(
            content=image_content,
            original_filename=original_filename,
            category="images",
            user_id=user_id,
        )

        result_json: dict = {
            "mode": mode,
            "source_type": "image",
            "bboxes": [],
            "llm_analysis": None,
        }

        try:
            if mode == "yolo_only":
                # Determine model path
                model_path = await self._resolve_yolo_model_path(model_id, user_id)
                bboxes = await self.yolo_service.detect(image_path, model_path=model_path)
                result_json["bboxes"] = bboxes

            elif mode == "llm_only":
                # Get LLM config
                llm_config = await self._resolve_llm_config(llm_config_id, user_id)
                # Encode image to base64
                img_b64 = self.image_service.encode_image_base64(image_path)
                # Call LLM
                llm_result = await self.llm_service.analyze_image(
                    api_base_url=llm_config.api_base_url,
                    api_key=decrypt_api_key(llm_config.api_key),
                    model_name=llm_config.model_name,
                    image_base64=img_b64,
                    provider=llm_config.provider,
                )
                result_json["llm_analysis"] = llm_result

            elif mode == "collaborative":
                # First: YOLO detection
                model_path = await self._resolve_yolo_model_path(model_id, user_id)
                bboxes = await self.yolo_service.detect(image_path, model_path=model_path)
                result_json["bboxes"] = bboxes

                # Get LLM config
                llm_config = await self._resolve_llm_config(llm_config_id, user_id)
                api_key = decrypt_api_key(llm_config.api_key)

                # Build YOLO context for LLM
                yolo_context = ""
                if bboxes:
                    yolo_objects = [f"{b['class_name']}(置信度 {b['confidence']:.0%})" for b in bboxes]
                    yolo_context = (
                        "YOLO 模型已检测到以下对象：" + "、".join(yolo_objects) + "。"
                        "请仅针对以上YOLO检测到的目标进行分析，不要描述图中未检测到的内容。"
                        "简要总结这些对象的核心特征，100字以内。"
                    )

                # Full image analysis with YOLO context
                img_b64 = self.image_service.encode_image_base64(image_path)
                llm_result = await self.llm_service.analyze_image(
                    api_base_url=llm_config.api_base_url,
                    api_key=api_key,
                    model_name=llm_config.model_name,
                    image_base64=img_b64,
                    provider=llm_config.provider,
                    prompt=yolo_context if yolo_context else None,
                )

                # Concurrent region analysis (max 3 at a time)
                semaphore = asyncio.Semaphore(3)
                region_tasks = []
                for i, bbox in enumerate(bboxes):
                    region_tasks.append(
                        self._analyze_region_with_semaphore(
                            semaphore=semaphore,
                            image_path=image_path,
                            bbox=bbox,
                            index=i,
                            llm_config=llm_config,
                            api_key=api_key,
                        )
                    )

                region_results = await asyncio.gather(*region_tasks, return_exceptions=True)
                region_analyses = []
                for i, res in enumerate(region_results):
                    if isinstance(res, Exception):
                        region_analyses.append({
                            "object": bboxes[i]["class_name"],
                            "description": f"Error: {str(res)}",
                        })
                    else:
                        region_analyses.append(res)

                llm_result["region_analyses"] = region_analyses
                result_json["llm_analysis"] = llm_result

            # Generate thumbnail
            thumbnail_path = await self.image_service.create_thumbnail(image_path, user_id)

            if save_record:
                # Persist detection record
                record = DetectionRecord(
                    user_id=user_id,
                    source_type="image",
                    source_path=image_path,
                    mode=mode,
                    yolo_model_id=model_id if mode != "llm_only" else None,
                    llm_config_id=llm_config_id if mode != "yolo_only" else None,
                    result_json=result_json,
                    thumbnail_path=thumbnail_path,
                )
                self.db.add(record)
                await self.db.flush()
                await self.db.refresh(record)
                record_id = record.id
            else:
                record_id = 0

            # Return the file path relative to backend for serving
            source_filename = os.path.basename(image_path)

            processing_time = (time.time() - start_time) * 1000

            return {
                "id": record_id,
                "mode": mode,
                "source_type": "image",
                "source_filename": source_filename,
                "bboxes": result_json.get("bboxes", []),
                "llm_analysis": result_json.get("llm_analysis"),
                "thumbnail_path": thumbnail_path,
                "processing_time_ms": round(processing_time, 2),
                "created_at": record.created_at.isoformat() if (save_record and record and record.created_at) else "",
            }

        except Exception as e:
            if save_record:
                # Save failure record
                record = DetectionRecord(
                    user_id=user_id,
                    source_type="image",
                    source_path=image_path,
                    mode=mode,
                    result_json={"error": str(e)},
                )
                self.db.add(record)
                await self.db.flush()
            raise

    async def _analyze_region_with_semaphore(
        self,
        semaphore: asyncio.Semaphore,
        image_path: str,
        bbox: dict,
        index: int,
        llm_config: LLMConfig,
        api_key: str,
    ) -> dict:
        """Analyze a cropped region with concurrency limit."""
        async with semaphore:
            # Crop the region
            region_b64 = await self.image_service.crop_region_base64(
                image_path,
                x1=bbox["x1"],
                y1=bbox["y1"],
                x2=bbox["x2"],
                y2=bbox["y2"],
            )
            return await self.llm_service.analyze_region(
                api_base_url=llm_config.api_base_url,
                api_key=api_key,
                model_name=llm_config.model_name,
                region_base64=region_b64,
                region_label=bbox["class_name"],
                provider=llm_config.provider,
            )

    async def _resolve_yolo_model_path(
        self, model_id: int | None, user_id: int
    ) -> str | None:
        """Resolve model_id to a file path, or return None for default."""
        if model_id is None or model_id == 0:
            return None  # Use default
        result = await self.db.execute(
            select(YOLOModel).where(
                YOLOModel.id == model_id,
                YOLOModel.user_id.in_([user_id, 0]),
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"YOLO model not found: {model_id}")
        return model.file_path

    async def _resolve_llm_config(
        self, llm_config_id: int | None, user_id: int
    ) -> LLMConfig:
        """Resolve LLM config, defaulting to active if not specified."""
        if llm_config_id is not None:
            result = await self.db.execute(
                select(LLMConfig).where(
                    LLMConfig.id == llm_config_id,
                    LLMConfig.user_id == user_id,
                )
            )
            config = result.scalar_one_or_none()
            if config is None:
                raise ValueError(f"LLM config not found: {llm_config_id}")
            return config

        # Default to active config
        result = await self.db.execute(
            select(LLMConfig).where(
                LLMConfig.user_id == user_id,
                LLMConfig.is_active == True,
            )
        )
        config = result.scalar_one_or_none()
        if config is None:
            raise ValueError("No active LLM configuration found. Please configure one first.")
        return config
