"""Detection history schemas."""

from pydantic import BaseModel


class HistoryListQuery(BaseModel):
    """Query parameters for history listing."""
    mode: str | None = None
    source_type: str | None = None
    page: int = 1
    page_size: int = 20


class HistoryItemResponse(BaseModel):
    """A single history record in the list."""
    id: int
    source_type: str
    source_path: str
    mode: str
    thumbnail_path: str | None = None
    result_json: dict | None = None
    created_at: str

    class Config:
        from_attributes = True


class HistoryDetailResponse(BaseModel):
    """Full detail of a detection history record."""
    id: int
    user_id: int
    source_type: str
    source_path: str
    mode: str
    yolo_model_id: int | None
    llm_config_id: int | None
    result_json: dict | None
    thumbnail_path: str | None
    created_at: str

    class Config:
        from_attributes = True


class PaginatedResponse(BaseModel):
    """Paginated list response wrapper."""
    total: int
    page: int
    page_size: int
    items: list[HistoryItemResponse]
