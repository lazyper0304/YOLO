"""YOLO model record."""

from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Integer, func, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.user import Base


class YOLOModel(Base):
    __tablename__ = "yolo_models"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    model_type: Mapped[str] = mapped_column(String(50), nullable=False, default="custom")  # builtin/custom
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    classes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )

    # Relationships
    owner: Mapped["User"] = relationship("User", back_populates="yolo_models")
