"""Service for logging and querying model call counts."""

from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.model_call_log import ModelCallLog


class ModelCallService:
    """Persists model usage calls to model_call_logs table."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_call(
        self,
        user_id: int,
        model_type: str,
        model_config_id: int | None = None,
        ref_id: int | None = None,
        metadata_json: dict | None = None,
    ) -> ModelCallLog:
        """Log a single model call."""
        log = ModelCallLog(
            user_id=user_id,
            model_type=model_type,
            model_config_id=model_config_id,
            ref_id=ref_id,
            metadata_json=metadata_json,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(log)
        return log

    async def get_call_counts(self, user_id: int) -> list[dict]:
        """Return call counts grouped by model_type for the given user."""
        rows = await self.db.execute(
            select(
                ModelCallLog.model_type,
                func.count(ModelCallLog.id).label("cnt"),
            )
            .where(ModelCallLog.user_id == user_id)
            .group_by(ModelCallLog.model_type)
        )
        return [
            {"name": row[0].capitalize() if row[0] != "embedding" else "嵌入模型",
             "value": row[1]}
            for row in rows.all()
        ]
