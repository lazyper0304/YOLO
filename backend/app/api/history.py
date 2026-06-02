"""Detection history API routes."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.detection_record import DetectionRecord

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=dict)
async def list_history(
    mode: str | None = Query(None),
    source_type: str | None = Query(None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List detection history with optional filtering and pagination."""
    conditions = [DetectionRecord.user_id == current_user.id]
    if mode:
        conditions.append(DetectionRecord.mode == mode)
    if source_type:
        conditions.append(DetectionRecord.source_type == source_type)

    # Count total
    count_query = select(func.count(DetectionRecord.id)).where(*conditions)
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Fetch page
    offset = (page - 1) * page_size
    query = (
        select(DetectionRecord)
        .where(*conditions)
        .order_by(desc(DetectionRecord.created_at))
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(query)
    records = result.scalars().all()

    items = []
    for r in records:
        items.append({
            "id": r.id,
            "source_type": r.source_type,
            "source_path": r.source_path,
            "mode": r.mode,
            "thumbnail_path": r.thumbnail_path,
            "result_json": r.result_json,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        })

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": items,
        },
    }


@router.get("/{record_id}", response_model=dict)
async def get_history_detail(
    record_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed information about a single detection record."""
    result = await db.execute(
        select(DetectionRecord).where(
            DetectionRecord.id == record_id,
            DetectionRecord.user_id == current_user.id,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Detection record not found",
        )

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "id": record.id,
            "user_id": record.user_id,
            "source_type": record.source_type,
            "source_path": record.source_path,
            "mode": record.mode,
            "yolo_model_id": record.yolo_model_id,
            "llm_config_id": record.llm_config_id,
            "result_json": record.result_json,
            "thumbnail_path": record.thumbnail_path,
            "created_at": record.created_at.isoformat() if record.created_at else "",
        },
    }
