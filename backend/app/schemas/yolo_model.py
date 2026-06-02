"""YOLO model schemas."""

from pydantic import BaseModel, Field


class YOLOModelCreate(BaseModel):
    """Create a YOLO model record."""
    name: str = Field(..., min_length=1, max_length=100)
    is_active: bool = False


class YOLOModelUpdate(BaseModel):
    """Update a YOLO model record."""
    name: str | None = Field(None, min_length=1, max_length=100)
    is_active: bool | None = None


class YOLOModelResponse(BaseModel):
    """YOLO model response."""
    id: int
    user_id: int
    name: str
    file_path: str
    model_type: str
    is_builtin: bool
    file_size: int
    is_active: bool
    uploaded_at: str

    class Config:
        from_attributes = True
