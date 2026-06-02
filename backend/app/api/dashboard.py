"""Dashboard API: stats and overview data."""

from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.detection_record import DetectionRecord
from app.models.yolo_model import YOLOModel
from app.models.llm_config import LLMConfig

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=dict)
async def dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return dashboard overview statistics."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # Total detections today
    today_count = await db.execute(
        select(func.count(DetectionRecord.id)).where(
            DetectionRecord.user_id == current_user.id,
            DetectionRecord.created_at >= today_start,
        )
    )
    today_total = today_count.scalar() or 0

    # Total detections all time
    all_time = await db.execute(
        select(func.count(DetectionRecord.id)).where(
            DetectionRecord.user_id == current_user.id,
        )
    )
    all_total = all_time.scalar() or 0

    # Mode breakdown
    mode_counts = {"yolo_only": 0, "llm_only": 0, "collaborative": 0}
    for mode in mode_counts:
        cnt = await db.execute(
            select(func.count(DetectionRecord.id)).where(
                DetectionRecord.user_id == current_user.id,
                DetectionRecord.mode == mode,
            )
        )
        mode_counts[mode] = cnt.scalar() or 0

    # Active YOLO models
    yolo_count = await db.execute(
        select(func.count(YOLOModel.id)).where(
            YOLOModel.user_id.in_([0, current_user.id]),
        )
    )
    total_yolo = yolo_count.scalar() or 0

    # LLM configs
    llm_count = await db.execute(
        select(func.count(LLMConfig.id)).where(
            LLMConfig.user_id == current_user.id,
        )
    )
    total_llm = llm_count.scalar() or 0

    # Recent detections
    recent = await db.execute(
        select(DetectionRecord).where(
            DetectionRecord.user_id == current_user.id,
        ).order_by(DetectionRecord.created_at.desc()).limit(5)
    )
    recent_items = []
    for r in recent.scalars().all():
        recent_items.append({
            "id": r.id,
            "mode": r.mode,
            "source_type": r.source_type,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        })

    return {
        "code": 0, "message": "ok",
        "data": {
            "today_detections": today_total,
            "total_detections": all_total,
            "mode_breakdown": mode_counts,
            "yolo_models": total_yolo,
            "llm_configs": total_llm,
            "recent_detections": recent_items,
        },
    }
