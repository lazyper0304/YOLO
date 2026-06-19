"""Task management service."""

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import DetectionRecord
from app.exceptions import NotFoundException, BusinessException


class TaskService:
    """Service for task CRUD, pause/resume, and batch operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_task(self, task_id: int, user_id: int) -> DetectionRecord:
        """Get a task by ID that belongs to the user, or raise NotFoundException."""
        result = await self.db.execute(
            select(DetectionRecord).where(
                DetectionRecord.id == task_id,
                DetectionRecord.user_id == user_id,
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise NotFoundException("任务不存在")
        return record

    async def list_user_tasks(
        self, user_id: int, page: int = 1, page_size: int = 20
    ) -> dict:
        """List tasks for user, newest first."""
        count_result = await self.db.execute(
            select(func.count(DetectionRecord.id)).where(
                DetectionRecord.user_id == user_id
            )
        )
        total = count_result.scalar() or 0

        result = await self.db.execute(
            select(DetectionRecord)
            .where(DetectionRecord.user_id == user_id)
            .order_by(DetectionRecord.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        records = result.scalars().all()

        items = [
            {
                "id": r.id,
                "mode": r.mode,
                "task_name": r.task_name or "",
                "source_type": r.source_type,
                "source_path": r.source_path,
                "status": r.status,
                "result_json": r.result_json,
                "thumbnail_path": r.thumbnail_path,
                "frame_interval_seconds": r.frame_interval_seconds,
                "progress": r.progress,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in records
        ]

        return {"items": items, "total": total, "page": page, "page_size": page_size}

    async def delete_task(self, task_id: int, user_id: int) -> None:
        """Delete a task. Raises BusinessException if task is running."""
        record = await self.get_user_task(task_id, user_id)
        if record.status == "running":
            raise BusinessException("任务正在运行，无法删除")
        await self.db.delete(record)
        await self.db.commit()

    async def pause_task(self, task_id: int, user_id: int) -> str:
        """Pause a pending task. Returns the resulting status."""
        record = await self.get_user_task(task_id, user_id)
        if record.status == "pending":
            record.status = "paused"
            await self.db.commit()
        return record.status

    async def resume_task(self, task_id: int, user_id: int) -> str:
        """Resume a paused task. Returns the resulting status."""
        record = await self.get_user_task(task_id, user_id)
        if record.status == "paused":
            record.status = "pending"
            await self.db.commit()
        return record.status

    async def batch_delete(self, ids: list[int], user_id: int) -> int:
        """Batch delete tasks (excluding running ones). Returns count processed."""
        result = await self.db.execute(
            select(DetectionRecord).where(
                DetectionRecord.id.in_(ids),
                DetectionRecord.user_id == user_id,
                DetectionRecord.status != "running",
            )
        )
        for record in result.scalars().all():
            await self.db.delete(record)
        await self.db.commit()
        return len(ids)
