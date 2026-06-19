"""Model call log for persisting model usage counts."""

from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, ForeignKey, JSON, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.user import Base


class ModelCallLog(Base):
    """Logs every call to any model (YOLO/LLM/OCR/Embedding).

    Each row represents a single invocation of a model by a user.
    Used by the dashboard to show per-model-type call counts.
    """
    __tablename__ = "model_call_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    model_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
        comment="模型类型: yolo / llm / ocr / embedding"
    )
    model_config_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="对应配置表的主键 ID (如 yolo_models.id), 可选"
    )
    ref_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="关联的业务记录 ID (如 detection_records.id), 可选"
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc),
        server_default=func.now(), index=True
    )
