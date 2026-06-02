"""Task management API: create, list, cancel detection tasks."""

import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.detection_record import DetectionRecord
from app.utils.file_utils import save_upload_file
from app.config import settings

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("", response_model=dict)
async def create_task(
    mode: str = Form(default="yolo_only"),
    task_name: str = Form(default=""),
    model_id: str | None = Form(default=None),
    llm_config_id: str | None = Form(default=None),
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

    content = await file.read()

    # Determine source type from filename
    source_type = "image"
    if file.filename and file.filename.lower().endswith(('.mp4', '.avi', '.mov', '.webm')):
        source_type = "video"
        if len(content) > settings.MAX_VIDEO_SIZE_BYTES:
            raise HTTPException(status_code=413, detail="视频文件大小超过限制")
    else:
        if len(content) > settings.MAX_IMAGE_SIZE_BYTES:
            raise HTTPException(status_code=413, detail="文件大小超过限制")

    # Save file
    image_path = await save_upload_file(
        content=content,
        original_filename=file.filename or "image",
        category="videos" if source_type == "video" else "images",
        user_id=current_user.id,
    )

    # Create pending task record
    record = DetectionRecord(
        user_id=current_user.id,
        source_type=source_type,
        source_path=image_path,
        mode=mode,
        task_name=task_name or None,
        yolo_model_id=parsed_model_id if mode != "llm_only" else None,
        llm_config_id=parsed_llm_id if mode != "yolo_only" else None,
        status="pending",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    return {
        "code": 0, "message": "ok",
        "data": {
            "id": record.id,
            "status": record.status,
            "mode": record.mode,
        },
    }


@router.get("", response_model=dict)
async def list_tasks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    page_size: int = 20,
):
    """List all tasks for the current user, newest first."""
    result = await db.execute(
        select(DetectionRecord)
        .where(DetectionRecord.user_id == current_user.id)
        .order_by(DetectionRecord.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    records = result.scalars().all()

    total = await db.execute(
        select(DetectionRecord).where(DetectionRecord.user_id == current_user.id)
    )
    # Just get the count
    count_result = await db.execute(
        select(DetectionRecord).where(DetectionRecord.user_id == current_user.id)
    )

    items = []
    for r in records:
        items.append({
            "id": r.id,
            "mode": r.mode,
            "task_name": r.task_name or "",
            "source_type": r.source_type,
            "source_path": r.source_path,
            "status": r.status,
            "result_json": r.result_json,
            "thumbnail_path": r.thumbnail_path,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        })

    return {
        "code": 0, "message": "ok",
        "data": {
            "total": len(items),
            "page": page,
            "page_size": page_size,
            "items": items,
        },
    }


@router.get("/{task_id}", response_model=dict)
async def get_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get task detail including full result."""
    result = await db.execute(
        select(DetectionRecord).where(
            DetectionRecord.id == task_id,
            DetectionRecord.user_id == current_user.id,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="任务不存在")

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

    return {
        "code": 0, "message": "ok",
        "data": {
            "id": record.id,
            "mode": record.mode,
            "source_type": record.source_type,
            "status": record.status,
            "result_json": record.result_json,
            "annotated_image": annotated_b64,
            "thumbnail_path": record.thumbnail_path,
            "created_at": record.created_at.isoformat() if record.created_at else "",
        },
    }


@router.delete("/{task_id}", response_model=dict)
async def delete_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a task record."""
    result = await db.execute(
        select(DetectionRecord).where(
            DetectionRecord.id == task_id,
            DetectionRecord.user_id == current_user.id,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    if record.status == "running":
        raise HTTPException(status_code=400, detail="任务正在运行，无法删除")

    await db.delete(record)
    await db.commit()
    return {"code": 0, "message": "ok", "data": None}


@router.post("/batch-delete", response_model=dict)
async def batch_delete(
    ids: list[int],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Batch delete task records."""
    result = await db.execute(
        select(DetectionRecord).where(
            DetectionRecord.id.in_(ids),
            DetectionRecord.user_id == current_user.id,
            DetectionRecord.status != "running",
        )
    )
    for record in result.scalars().all():
        await db.delete(record)
    await db.commit()
    return {"code": 0, "message": "ok", "data": {"deleted": len(ids)}}
