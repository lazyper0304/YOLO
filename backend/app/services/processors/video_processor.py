"""YOLO-only video processor with improved resource management and progress tracking."""

import os
import cv2
import tempfile
import logging
from typing import Callable
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.detection_record import DetectionRecord
from app.models.yolo_model import YOLOModel
from app.config import settings

logger = logging.getLogger(__name__)


class VideoProcessor:
    """YOLO-only video processing — every Nth frame detection, output annotated video.

    Features:
    - Configurable frame sampling interval
    - Progress callback support
    - Proper resource cleanup
    - Batch frame processing for efficiency
    """

    def __init__(self, db: AsyncSession, progress_callback: Callable[[int, int], None] | None = None):
        self.db = db
        self._progress_callback = progress_callback

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

        output_dir = os.path.join("uploads", "videos", str(record.user_id))
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"annotated_{record.id}.mp4")

        tmpdir_obj = tempfile.TemporaryDirectory(dir=settings.temp_dir)
        tmpdir = tmpdir_obj.name

        cap = None
        out = None

        try:
            cap = cv2.VideoCapture(record.source_path)
            if not cap.isOpened():
                raise ValueError(f"无法打开视频文件: {record.source_path}")

            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

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
                            x1, y1, x2, y2 = (
                                int(b["x1"]),
                                int(b["y1"]),
                                int(b["x2"]),
                                int(b["y2"]),
                            )
                            ci = hash(cls) % len(colors)
                            cv2.rectangle(frame, (x1, y1), (x2, y2), colors[ci], 2)
                            label = f"{cls} {b['confidence']:.0%}"
                            cv2.putText(
                                frame, label, (x1, y1 - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, colors[ci], 1,
                            )
                    except Exception as e:
                        logger.warning("Frame %d detection failed: %s", frame_idx, str(e))

                    out.write(frame)
                    processed += 1

                    # Report progress
                    if self._progress_callback and total_frames > 0:
                        progress = min(99, int((frame_idx / total_frames) * 100))
                        self._progress_callback(progress, processed)

                    # Periodic progress update to DB (every 10 processed frames)
                    if processed % 10 == 0:
                        record.progress = min(99, int((frame_idx / total_frames) * 100)) if total_frames > 0 else 0
                        await self.db.commit()

                frame_idx += 1

        finally:
            # Ensure resources are released
            if cap is not None:
                cap.release()
            if out is not None:
                out.release()
            tmpdir_obj.cleanup()

        # Build summary
        total_objects = sum(len(v) for v in all_detections.values())
        summary = []
        for cls, dets in sorted(all_detections.items(), key=lambda x: -len(x[1])):
            avg_conf = sum(d["confidence"] for d in dets) / len(dets)
            summary.append({
                "class": cls,
                "count": len(dets),
                "avg_confidence": round(avg_conf, 3),
            })

        record.result_json = {
            "mode": record.mode,
            "source_type": "video",
            "frame_count": processed,
            "total_frames": total_frames,
            "detection_summary": summary,
            "total_objects": total_objects,
            "video_path": output_path.replace("\\", "/"),
        }
        record.status = "completed"
        record.progress = 100

        # Final progress callback
        if self._progress_callback:
            self._progress_callback(100, processed)

        logger.info("Video processing complete: %d frames processed, %d objects detected",
                    processed, total_objects)
