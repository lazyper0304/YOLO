"""Detection API routes: image/video detection with YOLO and LLM."""

import os
import tempfile
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.detection import ImageDetectionQuery
from app.services.detection_service import DetectionService
from app.config import settings

router = APIRouter(prefix="/api/detection", tags=["detection"])


@router.post("/image", response_model=dict)
async def detect_image(
    file: UploadFile = File(...),
    mode: str = Form(default="yolo_only"),
    model_id: int | None = Form(default=None),
    llm_config_id: int | None = Form(default=None),
    llm_analysis_scope: str = Form(default="full"),
    kb_ids: str | None = Form(default=None),
    analysis_prompt: str | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload an image and run detection with the specified mode."""
    # Validate mode
    if mode not in ("yolo_only", "llm_only", "collaborative"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Mode must be one of: yolo_only, llm_only, collaborative",
        )

    # Parse kb_ids from comma-separated string
    parsed_kb_ids = None
    if kb_ids:
        try:
            parsed_kb_ids = [int(x.strip()) for x in kb_ids.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="kb_ids must be comma-separated integers",
            )

    # Validate file type
    allowed_extensions = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No file provided",
        )
    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported image format: {ext}",
        )

    # Read file content
    content = await file.read()
    if len(content) > settings.MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image file exceeds 20MB limit",
        )

    service = DetectionService(db)
    result = await service.process_image_detection(
        user_id=current_user.id,
        image_content=content,
        original_filename=file.filename,
        mode=mode,
        model_id=model_id,
        llm_config_id=llm_config_id,
        llm_analysis_scope=llm_analysis_scope,
        kb_ids=parsed_kb_ids,
        analysis_prompt=analysis_prompt,
    )

    return {"code": 0, "message": "ok", "data": result}


@router.post("/realtime", response_model=dict)
async def detect_realtime(
    file: UploadFile = File(...),
    model_id: int = Form(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Real-time YOLO detection — returns bboxes only, no persistence."""
    content = await file.read()
    if len(content) > settings.MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="图片过大")

    from app.models.yolo_model import YOLOModel
    from app.services.yolo_service import YOLOService

    r = await db.execute(select(YOLOModel).where(
        YOLOModel.id == model_id, YOLOModel.user_id == current_user.id
    ))
    model = r.scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=404, detail="模型不存在")

    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False, dir=settings.temp_dir)
    try:
        tmp.write(content)
        tmp.close()
        yolo = YOLOService()
        bboxes = await yolo.detect(tmp.name, model_path=model.file_path)
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass

    return {"code": 0, "message": "ok", "data": {"bboxes": bboxes}}
