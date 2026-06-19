"""User model."""

from datetime import datetime, timezone
from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        server_onupdate=func.now(),
    )

    # Relationships
    llm_configs: Mapped[list["LLMConfig"]] = relationship(
        "LLMConfig", back_populates="owner", cascade="all, delete-orphan"
    )
    yolo_models: Mapped[list["YOLOModel"]] = relationship(
        "YOLOModel", back_populates="owner", cascade="all, delete-orphan"
    )
    detection_records: Mapped[list["DetectionRecord"]] = relationship(
        "DetectionRecord", back_populates="owner", cascade="all, delete-orphan"
    )
    knowledge_bases: Mapped[list["KnowledgeBase"]] = relationship(
        "KnowledgeBase", back_populates="owner", cascade="all, delete-orphan"
    )
    embedding_configs: Mapped[list["EmbeddingModelConfig"]] = relationship(
        "EmbeddingModelConfig", back_populates="owner", cascade="all, delete-orphan"
    )
    ocr_configs: Mapped[list["OCRConfig"]] = relationship(
        "OCRConfig", back_populates="owner", cascade="all, delete-orphan"
    )
