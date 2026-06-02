"""Video service: frame extraction for video detection."""

import asyncio
import os
from pathlib import Path
from typing import Any


class VideoService:
    """Handles video processing: frame extraction for YOLO detection."""

    async def extract_frames(
        self, video_path: str, output_dir: str, frame_interval: int = 5
    ) -> list[str]:
        """Extract frames from a video at the specified interval (every N frames)."""
        import cv2

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._extract_frames_sync, video_path, output_dir, frame_interval
        )

    def _extract_frames_sync(
        self, video_path: str, output_dir: str, frame_interval: int
    ) -> list[str]:
        """Synchronous frame extraction using OpenCV."""
        import cv2

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Cannot open video file: {video_path}")

        Path(output_dir).mkdir(parents=True, exist_ok=True)

        frame_paths = []
        frame_count = 0
        saved_count = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_count % frame_interval == 0:
                filename = f"frame_{saved_count:06d}.jpg"
                filepath = os.path.join(output_dir, filename)
                cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                frame_paths.append(filepath)
                saved_count += 1

            frame_count += 1

        cap.release()
        return frame_paths

    async def get_video_info(self, video_path: str) -> dict:
        """Get video metadata (duration, fps, resolution)."""
        import cv2
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_video_info_sync, video_path)

    def _get_video_info_sync(self, video_path: str) -> dict:
        """Synchronous video info extraction."""
        import cv2
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Cannot open video file: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = frame_count / fps if fps > 0 else 0

        cap.release()
        return {
            "fps": round(fps, 2),
            "frame_count": frame_count,
            "width": width,
            "height": height,
            "duration_seconds": round(duration, 2),
        }
