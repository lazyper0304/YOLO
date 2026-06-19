"""File utility functions: validation, upload, path management."""

import os
import time
import hashlib
from pathlib import Path

from app.config import settings

# Allowed magic bytes for various file types
MAGIC_BYTES: dict[str, list[bytes]] = {
    "jpeg": [b"\xff\xd8\xff"],
    "jpg": [b"\xff\xd8\xff"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "webp": [b"RIFF"],
    "bmp": [b"BM"],
    "mp4": [b"\x00\x00\x00\x18ftypmp42", b"\x00\x00\x00\x1cftypmp42", b"\x00\x00\x00\x20ftypmp42"],
    "avi": [b"RIFF"],
    "mov": [b"\x00\x00\x00\x14ftypqt"],
    "pt": [],  # PyTorch files don't have consistent magic bytes
}

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".webm"}
ALLOWED_MODEL_EXTENSIONS = {".pt"}
ALLOWED_DOC_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}


def validate_file_magic(content: bytes, expected_type: str) -> bool:
    """Validate file content by checking magic bytes against expected type."""
    expected_type = expected_type.lower()
    if expected_type not in MAGIC_BYTES:
        return True  # Unknown type, skip magic bytes check

    expected_magics = MAGIC_BYTES[expected_type]
    if not expected_magics:
        return True  # No magic bytes defined for this type

    for magic in expected_magics:
        if content[: len(magic)] == magic:
            return True
    return False


def validate_file_extension(filename: str, allowed_extensions: set[str]) -> bool:
    """Validate the file extension against an allowed set."""
    ext = os.path.splitext(filename)[1].lower()
    return ext in allowed_extensions


async def save_upload_file(
    content: bytes,
    original_filename: str,
    category: str,
    user_id: int,
) -> str:
    """Save an uploaded file to the uploads directory and return the path."""
    upload_dir = Path(settings.UPLOAD_DIR)
    target_dir = upload_dir / category / str(user_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = int(time.time() * 1000)
    safe_filename = f"{timestamp}_{original_filename}"
    file_path = target_dir / safe_filename

    # Write the file
    with open(file_path, "wb") as f:
        f.write(content)

    # Return path with forward slashes for cross-platform compatibility
    return str(file_path).replace("\\", "/")


def create_upload_directories() -> None:
    """Create all required upload subdirectories on startup."""
    categories = ["images", "videos", "models", "thumbnails", "temp", "documents"]
    upload_dir = Path(settings.UPLOAD_DIR)
    for category in categories:
        (upload_dir / category).mkdir(parents=True, exist_ok=True)


def get_file_hash(content: bytes) -> str:
    """Compute SHA-256 hash of file content."""
    return hashlib.sha256(content).hexdigest()
