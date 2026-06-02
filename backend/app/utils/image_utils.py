"""Image utility functions."""

import io
import base64
from PIL import Image


def validate_image(content: bytes) -> tuple[bool, str]:
    """Validate that content is a valid image. Returns (is_valid, error_message)."""
    try:
        img = Image.open(io.BytesIO(content))
        img.verify()
        return True, ""
    except Exception as e:
        return False, str(e)


def get_image_dimensions(content: bytes) -> tuple[int, int]:
    """Get the (width, height) of an image from its bytes."""
    img = Image.open(io.BytesIO(content))
    return img.size


def resize_image(content: bytes, max_width: int = 1920, max_height: int = 1080) -> bytes:
    """Resize an image to fit within specified dimensions while maintaining aspect ratio."""
    img = Image.open(io.BytesIO(content)).convert("RGB")
    img.thumbnail((max_width, max_height), Image.LANCZOS)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


def image_to_base64(image_path: str) -> str:
    """Read an image file and return its base64 encoding."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
