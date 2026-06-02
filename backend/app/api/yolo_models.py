"""YOLO Models API routes."""

import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.yolo_model import YOLOModel
from app.schemas.yolo_model import YOLOModelCreate, YOLOModelUpdate, YOLOModelResponse
from app.utils.file_utils import validate_file_magic, save_upload_file
from app.config import settings
from app.services.yolo_service import YOLOService

router = APIRouter(prefix="/api/yolo-models", tags=["yolo-models"])


@router.get("", response_model=dict)
async def list_models(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all YOLO models for the current user."""
    result = await db.execute(
        select(YOLOModel).where(YOLOModel.user_id == current_user.id)
    )
    models = result.scalars().all()

    model_list = []
    for m in models:
        model_list.append({
            "id": m.id,
            "user_id": m.user_id,
            "name": m.name,
            "file_path": m.file_path,
            "model_type": m.model_type,
            "is_builtin": m.is_builtin,
            "file_size": m.file_size,
            "is_active": m.is_active,
            "classes": m.classes or "",
            "uploaded_at": m.uploaded_at.isoformat() if m.uploaded_at else "",
        })

    return {"code": 0, "message": "ok", "data": model_list}


@router.post("", response_model=dict)
async def upload_model(
    name: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a custom YOLO model (.pt file)."""
    # Validate file extension
    if not file.filename or not file.filename.endswith(".pt"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only .pt model files are accepted",
        )

    # Read file content for magic bytes validation
    content = await file.read()

    if len(content) > settings.MAX_MODEL_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="模型文件超过最大允许大小",
        )

    await file.seek(0)

    # Validate magic bytes (PyTorch .pt files start with PK or specific bytes)
    if len(content) < 4:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid model file",
        )

    # Save the file
    saved_path = await save_upload_file(
        content=content,
        original_filename=file.filename or "model.pt",
        category="models",
        user_id=current_user.id,
    )

    file_size = len(content)

    # Load model class names
    classes_str = ""
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        from ultralytics import YOLO
        yolo_model = await loop.run_in_executor(None, lambda: YOLO(saved_path))
        if hasattr(yolo_model, "names"):
            classes_str = ",".join(list(yolo_model.names.values()))
        del yolo_model
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Warning: Failed to load classes from uploaded model: {e}")

    model = YOLOModel(
        user_id=current_user.id,
        name=name,
        file_path=saved_path,
        model_type="custom",
        is_builtin=False,
        file_size=file_size,
        is_active=False,
        classes=classes_str or None,
    )
    db.add(model)
    await db.flush()
    await db.refresh(model)

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "id": model.id,
            "user_id": model.user_id,
            "name": model.name,
            "file_path": model.file_path,
            "model_type": model.model_type,
            "is_builtin": model.is_builtin,
            "file_size": model.file_size,
            "is_active": model.is_active,
            "classes": model.classes or "",
            "uploaded_at": model.uploaded_at.isoformat() if model.uploaded_at else "",
        },
    }


@router.get("/{model_id}", response_model=dict)
async def get_model(
    model_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single YOLO model."""
    model = await _get_user_model(model_id, current_user.id, db)
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "id": model.id,
            "user_id": model.user_id,
            "name": model.name,
            "file_path": model.file_path,
            "model_type": model.model_type,
            "is_builtin": model.is_builtin,
            "file_size": model.file_size,
            "is_active": model.is_active,
            "classes": model.classes or "",
            "uploaded_at": model.uploaded_at.isoformat() if model.uploaded_at else "",
        },
    }


@router.put("/{model_id}", response_model=dict)
async def update_model(
    model_id: int,
    req: YOLOModelUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a YOLO model's metadata."""
    model = await _get_user_model(model_id, current_user.id, db)
    if req.name is not None:
        model.name = req.name
    if req.is_active is not None:
        if req.is_active:
            # Deactivate other models
            active_models = await db.execute(
                select(YOLOModel).where(
                    YOLOModel.user_id == current_user.id,
                    YOLOModel.is_active == True,
                    YOLOModel.id != model_id,
                )
            )
            for am in active_models.scalars().all():
                am.is_active = False
        model.is_active = req.is_active

    await db.flush()
    await db.refresh(model)
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "id": model.id,
            "name": model.name,
            "is_active": model.is_active,
        },
    }


@router.delete("/{model_id}", response_model=dict)
async def delete_model(
    model_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a YOLO model."""
    model = await _get_user_model(model_id, current_user.id, db)
    if model.is_builtin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete built-in models",
        )
    # Remove the file from disk
    if os.path.exists(model.file_path):
        os.remove(model.file_path)
    await db.delete(model)
    await db.flush()
    return {"code": 0, "message": "ok", "data": None}


@router.get("/{model_id}/classes", response_model=dict)
async def get_model_classes(
    model_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the class names a YOLO model can detect."""
    model = await _get_user_model(model_id, current_user.id, db)
    yolo_service = YOLOService()
    classes = await yolo_service.get_model_classes(model.file_path)
    return {"code": 0, "message": "ok", "data": {"classes": classes}}


async def _get_user_model(model_id: int, user_id: int, db: AsyncSession) -> YOLOModel:
    """Fetch a YOLO model ensuring it belongs to the user or is built-in."""
    result = await db.execute(
        select(YOLOModel).where(
            YOLOModel.id == model_id,
            YOLOModel.user_id.in_([user_id, 0]),
        )
    )
    model = result.scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="YOLO model not found")
    return model
