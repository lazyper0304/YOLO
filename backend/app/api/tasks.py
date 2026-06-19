"""Task management API: create, list, cancel detection tasks."""

import os
from fastapi import APIRouter, Depends, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_db
from app.api import get_current_user, success_response
from app.models import User, DetectionRecord, LLMConfig, YOLOModel
from app.utils import save_upload_file
from app.config import settings
from app.exceptions import NotFoundException, BusinessException, ValidationException
from app.services.task_service import TaskService
from app.schemas.detection import AnalyzeFrameRequest

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _estimate_video_duration(video_path: str) -> float:
    """Estimate video duration in seconds using OpenCV. Returns 0 on failure."""
    import cv2
    try:
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        cap.release()
        if fps > 0:
            return total_frames / fps
    except Exception:
        pass
    return 0.0


def _estimate_llm_latency_per_frame(mode: str) -> float:
    """Estimated LLM latency per frame in seconds."""
    if mode == "yolo_only":
        return 1.0  # YOLO only, fast
    return 15.0  # LLM involved, slower


@router.post("", response_model=dict)
async def create_task(
    mode: str = Form(default="yolo_only"),
    task_name: str = Form(default=""),
    source_type: str = Form(default=""),
    model_id: str | None = Form(default=None),
    llm_config_id: str | None = Form(default=None),
    frame_interval_seconds: str | None = Form(default=None),
    analysis_prompt: str | None = Form(default=None),
    llm_analysis_scope: str = Form(default="full"),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a detection task (queued for background processing)."""
    # Parse optional IDs from string to int
    parsed_model_id: int | None = None
    parsed_llm_id: int | None = None
    try:
        if model_id and model_id != "null" and model_id != "undefined":
            parsed_model_id = int(model_id)
    except ValueError:
        pass
    try:
        if llm_config_id and llm_config_id != "null" and llm_config_id != "undefined":
            parsed_llm_id = int(llm_config_id)
    except ValueError:
        pass

    # Parse frame interval
    parsed_frame_interval: int = 5
    try:
        if frame_interval_seconds and frame_interval_seconds not in ("null", "undefined", ""):
            parsed_frame_interval = max(1, min(300, int(frame_interval_seconds)))
    except ValueError:
        pass

    content = await file.read()

    # Determine source type
    src_type = source_type or "image"
    if src_type == "image" and file.filename and file.filename.lower().endswith(('.mp4', '.avi', '.mov', '.webm')):
        src_type = "video"

    if src_type == "video":
        if len(content) > settings.MAX_VIDEO_SIZE_BYTES:
            raise ValidationException("视频文件大小超过限制")
    else:
        if len(content) > settings.MAX_IMAGE_SIZE_BYTES:
            raise ValidationException("图片文件大小超过限制")

    # Save file
    image_path = await save_upload_file(
        content=content,
        original_filename=file.filename or "image",
        category="videos" if src_type == "video" else "images",
        user_id=current_user.id,
    )

    # Estimate duration
    estimated_duration_seconds = 0.0
    estimated_frame_count = 0
    if src_type == "video" and parsed_frame_interval > 0:
        video_duration = _estimate_video_duration(image_path)
        if video_duration > 0:
            estimated_frame_count = int(video_duration / parsed_frame_interval)
            latency = _estimate_llm_latency_per_frame(mode)
            estimated_duration_seconds = estimated_frame_count * latency

    # Create pending task record
    record = DetectionRecord(
        user_id=current_user.id,
        source_type=src_type,
        source_path=image_path,
        mode=mode,
        task_name=task_name or None,
        yolo_model_id=parsed_model_id if mode != "llm_only" else None,
        llm_config_id=parsed_llm_id if mode != "yolo_only" else None,
        frame_interval_seconds=parsed_frame_interval,
        analysis_prompt=analysis_prompt or None,
        llm_analysis_scope=llm_analysis_scope,
        status="pending",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    return success_response(data={
        "id": record.id,
        "status": record.status,
        "mode": record.mode,
        "frame_interval_seconds": parsed_frame_interval,
        "estimated_frame_count": estimated_frame_count,
        "estimated_duration_seconds": round(estimated_duration_seconds, 1),
    })


@router.get("", response_model=dict)
async def list_tasks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    page_size: int = 20,
):
    """List all tasks for the current user, newest first."""
    service = TaskService(db)
    result = await service.list_user_tasks(current_user.id, page, page_size)
    return success_response(data=result)


@router.get("/{task_id}", response_model=dict)
async def get_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get task detail including full result."""
    service = TaskService(db)
    record = await service.get_user_task(task_id, current_user.id)

    # Generate annotated image if bboxes exist and image file exists
    annotated_b64: str | None = None
    bboxes = (record.result_json or {}).get("bboxes", [])
    if bboxes and record.source_path and os.path.exists(record.source_path):
        try:
            from app.services.image_service import ImageService
            img_service = ImageService()
            annotated_b64 = await img_service.draw_bboxes_base64(record.source_path, bboxes)
        except Exception:
            pass

    return success_response(data={
        "id": record.id,
        "mode": record.mode,
        "source_type": record.source_type,
        "status": record.status,
        "result_json": record.result_json,
        "annotated_image": annotated_b64,
        "thumbnail_path": record.thumbnail_path,
        "frame_interval_seconds": record.frame_interval_seconds,
        "analysis_prompt": record.analysis_prompt,
        "progress": record.progress,
        "created_at": record.created_at.isoformat() if record.created_at else "",
    })


@router.delete("/{task_id}", response_model=dict)
async def delete_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a task record."""
    service = TaskService(db)
    await service.delete_task(task_id, current_user.id)
    return success_response(data=None)


@router.post("/{task_id}/pause", response_model=dict)
async def pause_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pause a pending task (prevents queue from picking it up)."""
    service = TaskService(db)
    status = await service.pause_task(task_id, current_user.id)
    return success_response(data={"status": status})


@router.post("/{task_id}/resume", response_model=dict)
async def resume_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Resume a paused task (re-queue it)."""
    service = TaskService(db)
    status = await service.resume_task(task_id, current_user.id)
    return success_response(data={"status": status})


class UpdateResultRequest(BaseModel):
    bboxes: list[dict]


@router.post("/{task_id}/analyze-frame", response_model=dict)
async def analyze_frame(
    task_id: int,
    req: AnalyzeFrameRequest,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit a camera frame for LLM analysis. Frontend-driven async frame capture."""
    from app.services.llm_service import LLMService
    from app.services.image_service import ImageService
    from app.core import decrypt_api_key

    result = await db.execute(
        select(DetectionRecord).where(
            DetectionRecord.id == task_id,
            DetectionRecord.user_id == current_user.id,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise NotFoundException("任务不存在")

    if record.status not in ("running", "pending"):
        raise BusinessException("任务不在运行状态")

    # Update status if first frame
    if record.status == "pending":
        record.status = "running"
        await db.commit()

    # Resolve LLM config
    llm_config = None
    if record.llm_config_id:
        llm_result = await db.execute(
            select(LLMConfig).where(
                LLMConfig.id == record.llm_config_id,
                LLMConfig.user_id == current_user.id,
            )
        )
        llm_config = llm_result.scalar_one_or_none()

    if llm_config is None and record.mode != "yolo_only":
        # Try active config
        active_result = await db.execute(
            select(LLMConfig).where(
                LLMConfig.user_id == current_user.id,
                LLMConfig.is_active == True,
            )
        )
        llm_config = active_result.scalar_one_or_none()

    # Read frame image
    frame_content = await file.read()

    # Save frame
    from app.config import settings as app_settings
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False, dir=app_settings.temp_dir)
    try:
        tmp.write(frame_content)
        tmp.close()

        frame_result: dict = {"frame_index": req.frame_index, "time_seconds": req.time_seconds, "bboxes": []}

        # YOLO detection if mode supports it
        if record.mode in ("yolo_only", "collaborative"):
            from app.services.yolo_service import YOLOService
            yolo = YOLOService()
            model_path = None
            if record.yolo_model_id:
                yolo_result = await db.execute(
                    select(YOLOModel).where(YOLOModel.id == record.yolo_model_id)
                )
                ym = yolo_result.scalar_one_or_none()
                if ym:
                    model_path = ym.file_path
            bboxes = await yolo.detect(tmp.name, model_path=model_path)
            frame_result["bboxes"] = bboxes

        # LLM analysis
        if record.mode in ("llm_only", "collaborative") and llm_config:
            try:
                img_service = ImageService()
                img_b64 = img_service.encode_image_base64(tmp.name)
                llm_svc = LLMService()
                api_key = decrypt_api_key(llm_config.api_key)

                # Build prompt: theme prompt (per-frame with video context)
                prompt = record.analysis_prompt or None
                if prompt:
                    prompt = (
                        f"你正在分析一段视频中的单帧画面（第{req.frame_index}帧，时间{req.time_seconds:.1f}秒）。\n"
                        f"全视频分析主题：{prompt}\n\n"
                        f"请针对该帧画面进行观察，描述你看到的内容。"
                        f"以JSON格式返回：{{\"summary\":\"...\", \"objects_detected\":[...], \"detailed_analysis\":\"...\"}}"
                    )

                llm_result = await llm_svc.analyze_image(
                    api_base_url=llm_config.api_base_url,
                    api_key=api_key,
                    model_name=llm_config.model_name,
                    image_base64=img_b64,
                    prompt=prompt,
                    provider=llm_config.provider,
                )
                frame_result["llm_analysis"] = llm_result
            except Exception as e:
                frame_result["llm_analysis"] = {"error": str(e)}

        # Accumulate to task result
        rj = dict(record.result_json or {})
        rj["source_type"] = "camera"
        frames = rj.get("frames", [])
        frames.append(frame_result)
        rj["frames"] = frames

        # Update detection summary
        if frame_result.get("bboxes"):
            detections: dict[str, int] = {}
            existing = rj.get("detection_summary", [])
            for s in existing:
                detections[s["class"]] = s.get("count", 0)
            for b in frame_result["bboxes"]:
                cls = b.get("class_name", "unknown")
                detections[cls] = detections.get(cls, 0) + 1
            total = sum(detections.values())
            rj["detection_summary"] = sorted(
                [{"class": k, "count": v} for k, v in detections.items()],
                key=lambda x: -x["count"]
            )
            rj["total_objects"] = total

        record.result_json = rj
        await db.commit()

        return success_response(data=frame_result)
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


@router.post("/batch-delete", response_model=dict)
async def batch_delete(
    ids: list[int],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Batch delete task records."""
    service = TaskService(db)
    await service.batch_delete(ids, current_user.id)
    return success_response(data={"deleted": len(ids)})
