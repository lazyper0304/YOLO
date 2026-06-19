"""Detection history service."""

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import DetectionRecord
from app.exceptions import NotFoundException


class HistoryService:
    """Service for listing and retrieving detection history records."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_records(
        self,
        user_id: int,
        mode: str | None = None,
        source_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """List detection records with optional filtering and pagination."""
        conditions = [DetectionRecord.user_id == user_id]
        if mode:
            conditions.append(DetectionRecord.mode == mode)
        if source_type:
            conditions.append(DetectionRecord.source_type == source_type)

        count_query = select(func.count(DetectionRecord.id)).where(*conditions)
        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        offset = (page - 1) * page_size
        query = (
            select(DetectionRecord)
            .where(*conditions)
            .order_by(desc(DetectionRecord.created_at))
            .offset(offset)
            .limit(page_size)
        )
        result = await self.db.execute(query)
        records = result.scalars().all()

        items = [
            {
                "id": r.id,
                "source_type": r.source_type,
                "source_path": r.source_path,
                "mode": r.mode,
                "thumbnail_path": r.thumbnail_path,
                "result_json": r.result_json,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in records
        ]

        return {"items": items, "total": total, "page": page, "page_size": page_size}

    async def get_record(self, record_id: int, user_id: int) -> DetectionRecord:
        """Get a detection record by ID, ensuring it belongs to the user."""
        result = await self.db.execute(
            select(DetectionRecord).where(
                DetectionRecord.id == record_id,
                DetectionRecord.user_id == user_id,
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise NotFoundException("Detection record not found")
        return record
