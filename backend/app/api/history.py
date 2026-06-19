"""Detection history API routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_db
from app.api import get_current_user, success_response, paginated_response
from app.models import User
from app.services.history_service import HistoryService

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
    service = HistoryService(db)
    result = await service.list_records(
        current_user.id, mode=mode, source_type=source_type,
        page=page, page_size=page_size,
    )
    return paginated_response(**result)


@router.get("/{record_id}", response_model=dict)
async def get_history_detail(
    record_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed information about a single detection record."""
    service = HistoryService(db)
    record = await service.get_record(record_id, current_user.id)
    return success_response(data={
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
    })
