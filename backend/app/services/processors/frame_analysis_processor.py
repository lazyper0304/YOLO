"""Video processor with per-frame LLM analysis."""
import os
import cv2
import tempfile
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.detection_record import DetectionRecord
from app.models.yolo_model import YOLOModel
from app.models.llm_config import LLMConfig
from app.core.security import decrypt_api_key
from app.config import settings

logger = logging.getLogger(__name__)


class FrameAnalysisProcessor:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def process(self, record: DetectionRecord) -> None:
        """Video processing with LLM frame analysis at configurable intervals."""
        from app.services.yolo_service import YOLOService
        from app.services.llm_service import LLMService
        from app.services.image_service import ImageService
        from app.core.security import decrypt_api_key

        yolo = YOLOService()
        llm_svc = LLMService()
        img_svc = ImageService()

        model_path = None
        if record.yolo_model_id:
            r = await self.db.execute(select(YOLOModel).where(YOLOModel.id == record.yolo_model_id))
            m = r.scalar_one_or_none()
            if m:
                model_path = m.file_path

        llm_config = None
        if record.llm_config_id:
            r = await self.db.execute(select(LLMConfig).where(
                LLMConfig.id == record.llm_config_id, LLMConfig.user_id == record.user_id))
            llm_config = r.scalar_one_or_none()
        if llm_config is None:
            r = await self.db.execute(select(LLMConfig).where(
                LLMConfig.user_id == record.user_id, LLMConfig.is_active == True))
            llm_config = r.scalar_one_or_none()

        api_key = decrypt_api_key(llm_config.api_key) if llm_config else ""
        provider = llm_config.provider if llm_config else "generic"
        model_name = llm_config.model_name if llm_config else ""
        api_url = llm_config.api_base_url if llm_config else ""

        tmpdir_obj = tempfile.TemporaryDirectory(dir=settings.temp_dir)
        tmpdir = tmpdir_obj.name

        output_dir = os.path.join("uploads", "videos", str(record.user_id))
        os.makedirs(output_dir, exist_ok=True)
        thumbnail_dir = os.path.join("uploads", "thumbnails", str(record.user_id))
        os.makedirs(thumbnail_dir, exist_ok=True)

        interval_seconds = record.frame_interval_seconds or 5
        analysis_scope = getattr(record, "llm_analysis_scope", "full")

        try:
            cap = cv2.VideoCapture(record.source_path)
            video_fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            video_duration = total_frames / video_fps if video_fps > 0 else 0

            frames_per_interval = max(1, int(video_fps * interval_seconds))
            total_sample_frames = max(1, int(video_duration / interval_seconds)) if video_duration > 0 else 0

            all_frames: list[dict] = []
            all_detections: dict[str, int] = {}
            frame_idx = 0
            sample_idx = 0

            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                if frame_idx % frames_per_interval == 0 and sample_idx < total_sample_frames:
                    sample_idx += 1
                    time_sec = frame_idx / video_fps if video_fps > 0 else 0
                    fp = os.path.join(tmpdir, f"frame_{sample_idx:06d}.jpg")
                    cv2.imwrite(fp, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

                    frame_result: dict = {"frame_index": sample_idx, "time_seconds": round(time_sec, 1), "bboxes": []}

                    if record.mode in ("yolo_only", "collaborative"):
                        try:
                            bboxes = await yolo.detect(fp, model_path=model_path)
                            frame_result["bboxes"] = bboxes
                            for b in bboxes:
                                cls = b["class_name"]
                                all_detections[cls] = all_detections.get(cls, 0) + 1
                        except Exception as e:
                            logger.warning(f"YOLO frame {sample_idx} error: {e}")

                    if record.mode in ("llm_only", "collaborative") and llm_config:
                        try:
                            is_region_mode = record.mode == "collaborative" and analysis_scope == "region"

                            if not is_region_mode:
                                # Full-frame LLM analysis
                                img_b64 = img_svc.encode_image_base64(fp)
                                prompt = record.analysis_prompt or None
                                if prompt:
                                    prompt = (
                                        f"你正在分析一段视频中的第{sample_idx}/{total_sample_frames}帧"
                                        f"（时间{time_sec:.1f}秒，总时长{video_duration:.0f}秒）。\n"
                                        f"全视频分析主题：{prompt}\n\n"
                                        f"请针对该帧画面进行观察分析，描述你看到的内容，"
                                        f"注意与主题的关联性。"
                                        f"以JSON格式返回：{{\"summary\":\"...\", \"objects_detected\":[...], \"detailed_analysis\":\"...\"}}"
                                    )
                                llm_result = await llm_svc.analyze_image(
                                    api_base_url=api_url, api_key=api_key, model_name=model_name,
                                    image_base64=img_b64, prompt=prompt, provider=provider)
                                frame_result["llm_analysis"] = llm_result
                            else:
                                # Region-only mode: skip full-frame, analyze each detected region
                                region_analyses = []
                                for bbox in frame_result.get("bboxes", []):
                                    region_b64 = await img_svc.crop_region_base64(
                                        fp, x1=bbox["x1"], y1=bbox["y1"], x2=bbox["x2"], y2=bbox["y2"])
                                    region_result = await llm_svc.analyze_region(
                                        api_base_url=api_url, api_key=api_key, model_name=model_name,
                                        region_base64=region_b64, region_label=bbox["class_name"],
                                        provider=provider)
                                    region_analyses.append(region_result)
                                frame_result["llm_analysis"] = {
                                    "analysis_scope": "region",
                                    "region_analyses": region_analyses,
                                }

                        except Exception as e:
                            logger.warning(f"LLM frame {sample_idx} error: {e}")
                            frame_result["llm_analysis"] = {"error": str(e)}

                    try:
                        thumb_name = f"frame_{record.id}_{sample_idx}.jpg"
                        thumb_path = os.path.join(thumbnail_dir, thumb_name)
                        # Draw bboxes on thumbnail for visual confirmation
                        thumb_display = frame.copy()
                        colors = [(0,0,255),(0,255,0),(255,0,0),(0,255,255),(255,0,255),(255,255,0)]
                        for b in frame_result.get("bboxes", []):
                            x1, y1, x2, y2 = int(b["x1"]), int(b["y1"]), int(b["x2"]), int(b["y2"])
                            ci = hash(b.get("class_name","")) % len(colors)
                            cv2.rectangle(thumb_display, (x1, y1), (x2, y2), colors[ci], 2)
                            cv2.putText(thumb_display, f"{b['class_name']} {b['confidence']:.0%}",
                                        (x1, max(20, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, colors[ci], 1)
                        cv2.imwrite(thumb_path, cv2.resize(thumb_display, (320, 180)), [cv2.IMWRITE_JPEG_QUALITY, 75])
                        frame_result["thumbnail_path"] = thumb_path.replace("\\", "/")
                    except Exception:
                        pass

                    all_frames.append(frame_result)

                    if total_sample_frames > 0:
                        progress_pct = int(sample_idx / total_sample_frames * 100)
                        record.progress = progress_pct
                        summary = sorted([{"class": k, "count": v} for k, v in all_detections.items()], key=lambda x: -x["count"])
                        record.result_json = {
                            "mode": record.mode, "source_type": "video",
                            "frame_interval_seconds": interval_seconds,
                            "analysis_scope": analysis_scope,
                            "total_frames": total_sample_frames, "frames_completed": sample_idx,
                            "frames": all_frames, "detection_summary": summary,
                            "total_objects": sum(all_detections.values()),
                            "analysis_prompt": record.analysis_prompt,
                        }
                        await self.db.commit()
                frame_idx += 1
            cap.release()

            try:
                if all_frames and all_frames[0].get("thumbnail_path"):
                    record.thumbnail_path = all_frames[0]["thumbnail_path"]
                else:
                    thumb_name = f"video_{record.id}.jpg"
                    thumb_path = os.path.join(thumbnail_dir, thumb_name)
                    cap2 = cv2.VideoCapture(record.source_path)
                    ret, mid_frame = cap2.read()
                    cap2.release()
                    if ret:
                        cv2.imwrite(thumb_path, cv2.resize(mid_frame, (320, 180)), [cv2.IMWRITE_JPEG_QUALITY, 75])
                        record.thumbnail_path = thumb_path.replace("\\", "/")
            except Exception:
                pass
        finally:
            tmpdir_obj.cleanup()

        summary = sorted([{"class": k, "count": v} for k, v in all_detections.items()], key=lambda x: -x["count"])
        record.result_json = {
            "mode": record.mode, "source_type": "video",
            "frame_interval_seconds": interval_seconds,
            "analysis_scope": analysis_scope,
            "total_frames": len(all_frames),
            "frames_completed": len(all_frames), "frames": all_frames,
            "detection_summary": summary, "total_objects": sum(all_detections.values()),
            "analysis_prompt": record.analysis_prompt,
        }
        record.status = "completed"
        record.progress = 100
