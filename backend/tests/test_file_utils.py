"""Unit tests for file utility functions.

Covers: magic bytes validation, file extension validation, file saving,
directory creation, SHA-256 hashing.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.utils.file_utils import (
    MAGIC_BYTES,
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_VIDEO_EXTENSIONS,
    ALLOWED_MODEL_EXTENSIONS,
    validate_file_magic,
    validate_file_extension,
    save_upload_file,
    create_upload_directories,
    get_file_hash,
)


# ---------------------------------------------------------------------------
# Magic bytes validation
# ---------------------------------------------------------------------------

class TestValidateFileMagic:
    """Tests for validate_file_magic with various file signatures."""

    # ---- JPEG ----
    def test_valid_jpeg_magic(self):
        """A JPEG file starting with FF D8 FF passes."""
        content = b"\xff\xd8\xff" + b"\x00" * 100
        assert validate_file_magic(content, "jpeg") is True

    def test_valid_jpg_alias(self):
        """'jpg' and 'jpeg' map to the same magic check."""
        content = b"\xff\xd8\xff" + b"more data"
        assert validate_file_magic(content, "jpg") is True
        assert validate_file_magic(content, "jpeg") is True

    def test_invalid_jpeg_magic(self):
        """Random bytes must NOT pass JPEG validation."""
        assert validate_file_magic(b"GIF89a...", "jpeg") is False

    def test_jpeg_truncated_content(self):
        """Content shorter than magic bytes is handled safely."""
        assert validate_file_magic(b"\xff", "jpeg") is False
        assert validate_file_magic(b"", "jpeg") is False

    # ---- PNG ----
    def test_valid_png_magic(self):
        """Valid PNG signature passes."""
        png_header = b"\x89PNG\r\n\x1a\n"
        assert validate_file_magic(png_header + b"\x00" * 50, "png") is True

    def test_invalid_png_magic(self):
        assert validate_file_magic(b"\x89PNG\r\n", "png") is False

    # ---- WEBP ----
    def test_valid_webp_magic(self):
        """WEBP starts with 'RIFF'."""
        assert validate_file_magic(b"RIFF\x00\x00WEBP...", "webp") is True

    def test_invalid_webp_magic(self):
        assert validate_file_magic(b"NOT_WEBP", "webp") is False

    # ---- BMP ----
    def test_valid_bmp_magic(self):
        assert validate_file_magic(b"BM" + b"\x00" * 100, "bmp") is True

    def test_invalid_bmp_magic(self):
        assert validate_file_magic(b"XX", "bmp") is False

    # ---- MP4 ----
    def test_valid_mp4_magic(self):
        content = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 100
        assert validate_file_magic(content, "mp4") is True

    def test_invalid_mp4_magic(self):
        assert validate_file_magic(b"RANDOM", "mp4") is False

    # ---- Unknown / unsupported types ----
    def test_unknown_type_skips_check(self):
        """Unknown file types return True (skip magic check)."""
        assert validate_file_magic(b"anything", "pdf") is True
        assert validate_file_magic(b"", "unknown") is True

    def test_pt_type_skips_check(self):
        """.pt files have no magic byte definition → always True."""
        assert validate_file_magic(b"anything", "pt") is True

    def test_case_insensitive_type(self):
        """Type parameter is lowercased before lookup."""
        content = b"\xff\xd8\xff" + b"\x00" * 50
        assert validate_file_magic(content, "JPEG") is True
        assert validate_file_magic(content, "Jpg") is True

    # ---- Boundary: content exactly matches magic ----
    def test_content_exactly_magic(self):
        assert validate_file_magic(b"\xff\xd8\xff", "jpeg") is True
        assert validate_file_magic(b"BM", "bmp") is True


# ---------------------------------------------------------------------------
# File extension validation
# ---------------------------------------------------------------------------

class TestValidateFileExtension:
    """Tests for validate_file_extension."""

    def test_valid_image_extensions(self):
        for ext in ALLOWED_IMAGE_EXTENSIONS:
            assert validate_file_extension(f"photo{ext}", ALLOWED_IMAGE_EXTENSIONS) is True

    def test_valid_video_extensions(self):
        for ext in ALLOWED_VIDEO_EXTENSIONS:
            assert validate_file_extension(f"video{ext}", ALLOWED_VIDEO_EXTENSIONS) is True

    def test_valid_model_extensions(self):
        assert validate_file_extension("model.pt", ALLOWED_MODEL_EXTENSIONS) is True

    def test_invalid_extension(self):
        assert validate_file_extension("script.exe", ALLOWED_IMAGE_EXTENSIONS) is False
        assert validate_file_extension("doc.pdf", ALLOWED_IMAGE_EXTENSIONS) is False

    def test_case_insensitive_extension(self):
        assert validate_file_extension("photo.PNG", ALLOWED_IMAGE_EXTENSIONS) is True
        assert validate_file_extension("photo.Jpg", ALLOWED_IMAGE_EXTENSIONS) is True

    def test_no_extension(self):
        """Filename without extension returns False."""
        assert validate_file_extension("noextension", ALLOWED_IMAGE_EXTENSIONS) is False

    def test_multiple_dots(self):
        """Filename with multiple dots — only the last suffix is checked."""
        assert validate_file_extension("archive.tar.gz", ALLOWED_IMAGE_EXTENSIONS) is False
        assert validate_file_extension("photo.backup.jpg", ALLOWED_IMAGE_EXTENSIONS) is True

    def test_hidden_file(self):
        """Hidden Unix files are rejected."""
        assert validate_file_extension(".hidden", ALLOWED_IMAGE_EXTENSIONS) is False


# ---------------------------------------------------------------------------
# save_upload_file
# ---------------------------------------------------------------------------

class TestSaveUploadFile:
    """Tests for saving uploaded files."""

    @pytest.mark.asyncio
    async def test_saves_file_and_returns_path(self):
        """File is written to disk and the returned path exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.utils.file_utils.settings") as mock_settings:
                mock_settings.UPLOAD_DIR = tmpdir
                result = await save_upload_file(
                    content=b"hello world",
                    original_filename="test.txt",
                    category="images",
                    user_id=1,
                )
            assert os.path.exists(result)
            assert "images" in result
            assert "1" in result  # user_id directory
            with open(result, "rb") as f:
                assert f.read() == b"hello world"

    @pytest.mark.asyncio
    async def test_filename_contains_timestamp(self):
        """Saved filename is prefixed with a timestamp."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.utils.file_utils.settings") as mock_settings:
                mock_settings.UPLOAD_DIR = tmpdir
                result = await save_upload_file(
                    content=b"data",
                    original_filename="image.jpg",
                    category="images",
                    user_id=2,
                )
            basename = os.path.basename(result)
            # Format: <timestamp>_image.jpg
            parts = basename.split("_", 1)
            assert len(parts) == 2
            assert parts[0].isdigit()  # timestamp
            assert parts[1] == "image.jpg"

    @pytest.mark.asyncio
    async def test_creates_nested_directories(self):
        """Missing directories are created automatically."""
        with tempfile.TemporaryDirectory() as tmpdir:
            deep_path = os.path.join(tmpdir, "deep", "nested")
            with patch("app.utils.file_utils.settings") as mock_settings:
                mock_settings.UPLOAD_DIR = deep_path
                result = await save_upload_file(
                    content=b"x",
                    original_filename="f.txt",
                    category="images",
                    user_id=99,
                )
            assert os.path.exists(result)

    @pytest.mark.asyncio
    async def test_special_characters_in_filename(self):
        """Filenames with special characters are preserved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.utils.file_utils.settings") as mock_settings:
                mock_settings.UPLOAD_DIR = tmpdir
                result = await save_upload_file(
                    content=b"x",
                    original_filename="My Image (1).jpg",
                    category="images",
                    user_id=1,
                )
            assert os.path.exists(result)
            assert "My Image (1).jpg" in result

    @pytest.mark.asyncio
    async def test_empty_content(self):
        """Empty file content is saved as an empty file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.utils.file_utils.settings") as mock_settings:
                mock_settings.UPLOAD_DIR = tmpdir
                result = await save_upload_file(
                    content=b"",
                    original_filename="empty.txt",
                    category="temp",
                    user_id=1,
                )
            assert os.path.exists(result)
            assert os.path.getsize(result) == 0


# ---------------------------------------------------------------------------
# create_upload_directories
# ---------------------------------------------------------------------------

class TestCreateUploadDirectories:
    """Tests for directory scaffolding."""

    def test_creates_all_expected_dirs(self):
        """All five category directories are created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.utils.file_utils.settings") as mock_settings:
                mock_settings.UPLOAD_DIR = tmpdir
                create_upload_directories()

            expected = ["images", "videos", "models", "thumbnails", "temp"]
            for cat in expected:
                cat_path = Path(tmpdir) / cat
                assert cat_path.exists()
                assert cat_path.is_dir()

    def test_idempotent(self):
        """Calling create_upload_directories twice does not fail."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.utils.file_utils.settings") as mock_settings:
                mock_settings.UPLOAD_DIR = tmpdir
                create_upload_directories()
                create_upload_directories()  # should not raise


# ---------------------------------------------------------------------------
# get_file_hash
# ---------------------------------------------------------------------------

class TestGetFileHash:
    """Tests for SHA-256 file hashing."""

    def test_known_hash(self):
        """SHA-256 of known content is deterministic."""
        import hashlib
        content = b"hello world"
        expected = hashlib.sha256(content).hexdigest()
        assert get_file_hash(content) == expected

    def test_different_content_different_hash(self):
        assert get_file_hash(b"a") != get_file_hash(b"b")

    def test_empty_content(self):
        import hashlib
        assert get_file_hash(b"") == hashlib.sha256(b"").hexdigest()

    def test_large_content(self):
        """Large content hashing works."""
        content = b"x" * (10 * 1024 * 1024)  # 10 MB
        h = get_file_hash(content)
        assert len(h) == 64  # SHA-256 hex digest is 64 chars
