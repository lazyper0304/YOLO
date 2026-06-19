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


class FrameAnalysisResult(BaseModel):
    """Single frame analysis result in video/camera tasks."""
    frame_index: int
    time_seconds: float
    bboxes: list[BBoxItem] = []
    llm_analysis: LLMAnalysisResult | None = None
    thumbnail_path: str | None = None


class VideoAnalysisOptions(BaseModel):
    """Options for video/camera LLM frame analysis."""
    frame_interval_seconds: int = Field(default=5, ge=1, le=300)
    analysis_prompt: str | None = None  # 全视频主题分析提示词


class GeneratePromptRequest(BaseModel):
    """Request for LLM to generate an analysis prompt."""
    requirement: str  # 用户自然语言描述的分析需求
    llm_config_id: int | None = None


class AnalyzeFrameRequest(BaseModel):
    """Request for analyzing a single camera frame."""
    frame_index: int
    time_seconds: float
