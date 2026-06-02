"""Detection schemas for image/video detection requests and results."""

from pydantic import BaseModel, Field


class BBoxItem(BaseModel):
    """A single bounding box result."""
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    class_name: str
    class_id: int


class LLMAnalysisResult(BaseModel):
    """LLM analysis result for a detection."""
    summary: str = ""
    objects_detected: list[str] = []
    detailed_analysis: str = ""
    region_analyses: list[dict] = []


class DetectionResult(BaseModel):
    """Full detection result returned to the client."""
    mode: str
    source_type: str
    bboxes: list[BBoxItem] = []
    llm_analysis: LLMAnalysisResult | None = None
    annotated_image_base64: str | None = None
    processing_time_ms: float = 0.0


class ImageDetectionQuery(BaseModel):
    """Query parameters for image detection."""
    mode: str = Field(default="yolo_only", pattern=r"^(yolo_only|llm_only|collaborative)$")
    model_id: int | None = None
    llm_config_id: int | None = None
