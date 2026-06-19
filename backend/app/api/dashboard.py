"""Dashboard API: stats and overview data."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_db
from app.api import get_current_user, success_response
from app.models import User
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=dict)
async def dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return dashboard overview statistics."""
    try:
        service = DashboardService(db)
        stats = await service.get_stats(current_user.id)
        return success_response(data=stats)
    except Exception:
        return success_response(data={
            "today_detections": 0, "total_detections": 0,
            "mode_breakdown": {"yolo_only": 0, "llm_only": 0, "collaborative": 0},
            "yolo_models": 0, "llm_configs": 0, "recent_detections": [],
        })


@router.get("/daily")
async def daily_stats(
    days: int = 14,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return daily detection counts for charts."""
    service = DashboardService(db)
    data = await service.get_daily_stats(current_user.id, days)
    return success_response(data=data)


@router.get("/mode-pie")
async def mode_pie(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return mode breakdown for pie chart."""
    service = DashboardService(db)
    data = await service.get_mode_pie(current_user.id)
    return success_response(data=data)


@router.get("/model-calls")
async def model_calls(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return model call counts (YOLO/LLM/OCR/Embedding) for pie chart."""
    service = DashboardService(db)
    data = await service.get_model_calls(current_user.id)
    return success_response(data=data)
