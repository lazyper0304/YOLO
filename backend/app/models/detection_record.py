"""Detection record model."""

from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, func, Text, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.user import Base


class DetectionRecord(Base):
    __tablename__ = "detection_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)  # image/video/camera
    source_path: Mapped[str] = mapped_column(String(500), nullable=False)
    mode: Mapped[str] = mapped_column(String(30), nullable=False)  # yolo_only/llm_only/collaborative
    task_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    yolo_model_id: Mapped[int | None] = mapped_column(ForeignKey("yolo_models.id", ondelete="SET NULL"), nullable=True)
    llm_config_id: Mapped[int | None] = mapped_column(ForeignKey("llm_configs.id", ondelete="SET NULL"), nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")  # pending/running/completed/failed
    thumbnail_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    frame_interval_seconds: Mapped[int] = mapped_column(Integer, default=5, server_default="5")  # 截帧间隔(秒), 1-300
    analysis_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)  # 全视频主题分析提示词
    progress: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # 处理进度 0-100
    llm_analysis_scope: Mapped[str] = mapped_column(String(20), default="full", server_default="full")  # LLM分析范围: full/region
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )

    # Relationships
    owner: Mapped["User"] = relationship("User", back_populates="detection_records")
    yolo_model: Mapped["YOLOModel | None"] = relationship("YOLOModel")
    llm_config: Mapped["LLMConfig | None"] = relationship("LLMConfig")
