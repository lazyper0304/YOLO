"""Background task queue service for parallel detection processing."""

import asyncio
import logging
import os
import tempfile

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.detection_record import DetectionRecord

logger = logging.getLogger(__name__)


class TaskQueue:
    """Simple in-memory task queue with background workers."""

    _instance: "TaskQueue | None" = None
    _max_workers = 1

    def __new__(cls) -> "TaskQueue":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._semaphore = asyncio.Semaphore(self._max_workers)
        self._running = False

    async def start(self):
        self._running = True
        asyncio.create_task(self._process_loop())

    async def stop(self):
        self._running = False

    async def _process_loop(self):
        from app.core.database import async_session_factory

        while self._running:
            try:
                task_id = None
                async with async_session_factory() as db:
                    result = await db.execute(
                        select(DetectionRecord)
                        .where(DetectionRecord.status == "pending")
                        .order_by(DetectionRecord.created_at.asc())
                        .limit(1)
                        .with_for_update(skip_locked=True)
                    )
                    record = result.scalar_one_or_none()

                    if record is None:
                        await db.commit()
                        await asyncio.sleep(1)
                        continue

                    task_id = record.id
                    record.status = "running"
                    await db.commit()

                if task_id is None:
                    continue

                async with self._semaphore:
                    async with async_session_factory() as proc_db:
                        try:
                            fresh = await proc_db.execute(
                                select(DetectionRecord).where(DetectionRecord.id == task_id)
                            )
                            fresh_record = fresh.scalar_one_or_none()
                            if fresh_record is None:
                                continue

                            if not os.path.exists(fresh_record.source_path):
                                raise FileNotFoundError(f"Source not found: {fresh_record.source_path}")

                            if fresh_record.source_type == "video":
                                await self._process_video(proc_db, fresh_record)
                            else:
                                await self._process_image(proc_db, fresh_record)

                            await proc_db.commit()

                        except Exception as e:
                            if fresh_record:
                                fresh_record.result_json = {"error": str(e)}
                                fresh_record.status = "failed"
                                await proc_db.commit()
                            logger.error(f"Task {task_id} failed: {e}")

            except Exception as e:
                logger.error(f"Task queue error: {e}")
                await asyncio.sleep(2)

    async def _process_image(self, db: AsyncSession, record: DetectionRecord):
        from app.services.detection_service import DetectionService
        service = DetectionService(db)
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
        )
        record.result_json = {
            "mode": result["mode"],
            "bboxes": result["bboxes"],
            "llm_analysis": result["llm_analysis"],
        }
        record.status = "completed"
        record.thumbnail_path = result.get("thumbnail_path")

    async def _process_video(self, db: AsyncSession, record: DetectionRecord):
        from app.services.yolo_service import YOLOService
        import cv2

        yolo = YOLOService()
        model_path = None
        if record.yolo_model_id:
            from app.models.yolo_model import YOLOModel
            r = await db.execute(select(YOLOModel).where(YOLOModel.id == record.yolo_model_id))
            m = r.scalar_one_or_none()
            if m:
                model_path = m.file_path

        output_dir = os.path.join("uploads", "videos", str(record.user_id))
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"annotated_{record.id}.mp4")

        from app.config import settings
        tmpdir_obj = tempfile.TemporaryDirectory(dir=settings.temp_dir)
        tmpdir = tmpdir_obj.name

        try:
            cap = cv2.VideoCapture(record.source_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fourcc = cv2.VideoWriter_fourcc(*'avc1')
            out = cv2.VideoWriter(output_path, fourcc, fps / 5, (width, height))

            all_detections: dict[str, list[dict]] = {}
            frame_idx = 0
            processed = 0
            colors = [(0, 0, 255), (0, 255, 0), (255, 0, 0), (0, 255, 255), (255, 0, 255)]

            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                if frame_idx % 5 == 0:
                    fp = os.path.join(tmpdir, f"f{processed:06d}.jpg")
                    cv2.imwrite(fp, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    try:
                        bboxes = await yolo.detect(fp, model_path=model_path)
                        for b in bboxes:
                            cls = b["class_name"]
                            if cls not in all_detections:
                                all_detections[cls] = []
                            all_detections[cls].append(b)
                            x1, y1, x2, y2 = int(b["x1"]), int(b["y1"]), int(b["x2"]), int(b["y2"])
                            ci = hash(cls) % len(colors)
                            cv2.rectangle(frame, (x1, y1), (x2, y2), colors[ci], 2)
                            label = f"{cls} {b['confidence']:.0%}"
                            cv2.putText(frame, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, colors[ci], 1)
                    except Exception:
                        pass
                    out.write(frame)
                    processed += 1
                frame_idx += 1

            cap.release()
            out.release()
        finally:
            tmpdir_obj.cleanup()

        total_objects = sum(len(v) for v in all_detections.values())
        summary = []
        for cls, dets in sorted(all_detections.items(), key=lambda x: -len(x[1])):
            avg_conf = sum(d["confidence"] for d in dets) / len(dets)
            summary.append({"class": cls, "count": len(dets), "avg_confidence": round(avg_conf, 3)})

        record.result_json = {
            "mode": record.mode,
            "source_type": "video",
            "frame_count": processed,
            "detection_summary": summary,
            "total_objects": total_objects,
            "video_path": output_path.replace("\\", "/"),
        }
        record.status = "completed"
