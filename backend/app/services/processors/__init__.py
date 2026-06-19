"""Task processors for different source types."""
from app.services.processors.image_processor import ImageProcessor
from app.services.processors.video_processor import VideoProcessor
from app.services.processors.frame_analysis_processor import FrameAnalysisProcessor
from app.services.processors.camera_processor import CameraIPProcessor, CameraWebcamProcessor

__all__ = [
    "ImageProcessor",
    "VideoProcessor",
    "FrameAnalysisProcessor",
    "CameraIPProcessor",
    "CameraWebcamProcessor",
]
