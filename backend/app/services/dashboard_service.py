"""Dashboard statistics service."""

from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import DetectionRecord, YOLOModel, LLMConfig, KBDocument, KBChunk


class DashboardService:
    """Service for computing dashboard overview statistics."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_stats(self, user_id: int) -> dict:
        """Return dashboard overview statistics for the given user."""
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        total_result = await self.db.execute(
            select(func.count(DetectionRecord.id)).where(
                DetectionRecord.user_id == user_id
            )
        )
        all_total = total_result.scalar() or 0

        today_result = await self.db.execute(
            select(func.count(DetectionRecord.id)).where(
                DetectionRecord.user_id == user_id,
                DetectionRecord.created_at >= today_start,
            )
        )
        today_total = today_result.scalar() or 0

        mode_counts: dict[str, int] = {"yolo_only": 0, "llm_only": 0, "collaborative": 0}
        for mode in mode_counts:
            cnt = await self.db.execute(
                select(func.count(DetectionRecord.id)).where(
                    DetectionRecord.user_id == user_id,
                    DetectionRecord.mode == mode,
                )
            )
            mode_counts[mode] = cnt.scalar() or 0

        yolo_count = await self.db.execute(
            select(func.count(YOLOModel.id)).where(
                YOLOModel.user_id.in_([0, user_id])
            )
        )
        total_yolo = yolo_count.scalar() or 0

        llm_count = await self.db.execute(
            select(func.count(LLMConfig.id)).where(
                LLMConfig.user_id == user_id
            )
        )
        total_llm = llm_count.scalar() or 0

        recent_result = await self.db.execute(
            select(DetectionRecord)
            .where(DetectionRecord.user_id == user_id)
            .order_by(DetectionRecord.created_at.desc())
            .limit(5)
        )
        recent_items = []
        for r in recent_result.scalars().all():
            recent_items.append({
                "id": r.id,
                "mode": r.mode,
                "source_type": r.source_type,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            })

        return {
            "today_detections": today_total,
            "total_detections": all_total,
            "mode_breakdown": mode_counts,
            "yolo_models": total_yolo,
            "llm_configs": total_llm,
            "recent_detections": recent_items,
        }

    async def get_daily_stats(self, user_id: int, days: int = 14) -> dict:
        """Return daily detection counts for the past N days (line/bar chart data)."""
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        start_date = today - timedelta(days=days - 1)

        # Query daily counts
        rows = await self.db.execute(
            select(
                cast(DetectionRecord.created_at, Date).label("day"),
                func.count(DetectionRecord.id).label("cnt"),
            )
            .where(
                DetectionRecord.user_id == user_id,
                DetectionRecord.created_at >= start_date,
            )
            .group_by(cast(DetectionRecord.created_at, Date))
            .order_by(cast(DetectionRecord.created_at, Date))
        )

        daily_map: dict[str, int] = {}
        for row in rows.all():
            day_str = row[0].isoformat() if row[0] else ""
            daily_map[day_str] = row[1]

        # Fill missing days with zero
        dates = []
        counts = []
        for i in range(days):
            d = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
            dates.append(d)
            counts.append(daily_map.get(d, 0))

        return {"dates": dates, "counts": counts}

    async def get_mode_pie(self, user_id: int) -> dict:
        """Return mode breakdown for pie chart."""
        mode_counts: dict[str, int] = {"yolo_only": 0, "llm_only": 0, "collaborative": 0}
        for mode in mode_counts:
            cnt = await self.db.execute(
                select(func.count(DetectionRecord.id)).where(
                    DetectionRecord.user_id == user_id,
                    DetectionRecord.mode == mode,
                )
            )
            mode_counts[mode] = cnt.scalar() or 0

        labels_map = {"yolo_only": "YOLO", "llm_only": "LLM", "collaborative": "协同"}
        return {
            "series": [
                {"name": labels_map.get(k, k), "value": v}
                for k, v in mode_counts.items()
            ]
        }

    async def get_model_calls(self, user_id: int) -> dict:
        """Return call counts for each model type (YOLO/LLM/OCR/Embedding)."""
        # YOLO calls: detection records that used YOLO (yolo_only + collaborative)
        yolo_cnt = await self.db.execute(
            select(func.count(DetectionRecord.id)).where(
                DetectionRecord.user_id == user_id,
                DetectionRecord.mode.in_(["yolo_only", "collaborative"]),
            )
        )
        yolo_calls = yolo_cnt.scalar() or 0

        # LLM calls: detection records that used LLM (llm_only + collaborative)
        llm_cnt = await self.db.execute(
            select(func.count(DetectionRecord.id)).where(
                DetectionRecord.user_id == user_id,
                DetectionRecord.mode.in_(["llm_only", "collaborative"]),
            )
        )
        llm_calls = llm_cnt.scalar() or 0

        # OCR calls: KB documents processed (each document may trigger OCR)
        ocr_cnt = await self.db.execute(
            select(func.count(KBDocument.id)).where(
                KBDocument.user_id == user_id,
            )
        )
        ocr_calls = ocr_cnt.scalar() or 0

        # Embedding calls: KB chunks created (each chunk = one embedding vector)
        embed_cnt = await self.db.execute(
            select(func.count(KBChunk.id)).select_from(KBChunk).join(
                KBDocument, KBChunk.document_id == KBDocument.id
            ).where(
                KBDocument.user_id == user_id,
            )
        )
        embed_calls = embed_cnt.scalar() or 0

        return {
            "series": [
                {"name": "YOLO", "value": yolo_calls},
                {"name": "LLM", "value": llm_calls},
                {"name": "OCR", "value": ocr_calls},
                {"name": "嵌入模型", "value": embed_calls},
            ]
        }
