"""Image service: PIL-based image manipulation, bbox drawing, cropping, encoding."""

import base64
import io
import os
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.config import settings


class ImageService:
    """Handles image manipulation: bbox drawing, cropping, encoding, thumbnails."""

    # Color palette for different classes
    COLORS: list[tuple[int, int, int]] = [
        (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0),
        (255, 0, 255), (0, 255, 255), (128, 0, 0), (0, 128, 0),
        (0, 0, 128), (128, 128, 0), (128, 0, 128), (0, 128, 128),
        (255, 128, 0), (255, 0, 128), (128, 255, 0), (0, 255, 128),
    ]

    def _get_color(self, class_id: int) -> tuple[int, int, int]:
        """Get a consistent color for a class ID."""
        return self.COLORS[class_id % len(self.COLORS)]

    async def draw_bboxes_base64(self, image_path: str, bboxes: list[dict]) -> str:
        """Draw bounding boxes on an image and return as base64 string."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._draw_bboxes_sync, image_path, bboxes)

    def _draw_bboxes_sync(self, image_path: str, bboxes: list[dict]) -> str:
        """Synchronous bbox drawing."""
        img = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(img)

        # Try to load a font, fall back to default
        try:
            font = ImageFont.truetype("arial.ttf", 14)
        except (IOError, OSError):
            font = ImageFont.load_default()

        for bbox in bboxes:
            x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]
            color = self._get_color(bbox.get("class_id", 0))
            class_name = bbox.get("class_name", "unknown")
            confidence = bbox.get("confidence", 0.0)

            # Draw rectangle
            draw.rectangle([x1, y1, x2, y2], outline=color, width=2)

            # Draw label background
            label = f"{class_name} {confidence:.2f}"
            try:
                bbox_text = draw.textbbox((x1, y1 - 18), label, font=font)
            except AttributeError:
                tw, th = draw.textsize(label, font=font)
                bbox_text = (x1, y1 - th - 4, x1 + tw, y1)
            draw.rectangle(bbox_text, fill=color)
            draw.text((x1, y1 - 18), label, fill=(255, 255, 255), font=font)

        # Encode to base64
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    async def crop_region_base64(
        self, image_path: str, x1: float, y1: float, x2: float, y2: float
    ) -> str:
        """Crop a region from the image and return as base64."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._crop_region_sync, image_path, x1, y1, x2, y2
        )

    def _crop_region_sync(
        self, image_path: str, x1: float, y1: float, x2: float, y2: float
    ) -> str:
        """Synchronous region crop."""
        img = Image.open(image_path).convert("RGB")
        # Add some padding
        pad = 10
        x1_p = max(0, int(x1) - pad)
        y1_p = max(0, int(y1) - pad)
        x2_p = min(img.width, int(x2) + pad)
        y2_p = min(img.height, int(y2) + pad)

        cropped = img.crop((x1_p, y1_p, x2_p, y2_p))
        buffer = io.BytesIO()
        cropped.save(buffer, format="JPEG", quality=85)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def encode_image_base64(self, image_path: str) -> str:
        """Encode an entire image to base64 string."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    async def create_thumbnail(self, image_path: str, user_id: int, size: tuple = (200, 200)) -> str:
        """Create a thumbnail and return its path."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._create_thumbnail_sync, image_path, user_id, size)

    def _create_thumbnail_sync(self, image_path: str, user_id: int, size: tuple) -> str:
        """Synchronous thumbnail creation."""
        upload_dir = Path(settings.UPLOAD_DIR)
        thumb_dir = upload_dir / "thumbnails" / str(user_id)
        thumb_dir.mkdir(parents=True, exist_ok=True)

        filename = os.path.basename(image_path)
        thumb_path = thumb_dir / f"thumb_{filename}"

        img = Image.open(image_path).convert("RGB")
        img.thumbnail(size, Image.LANCZOS)
        img.save(str(thumb_path), format="JPEG", quality=80)
        return str(thumb_path)
