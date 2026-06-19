"""OCR service — extracts text from images via custom API."""

import base64
import json
import logging
import os

import httpx

logger = logging.getLogger(__name__)


class OCRService:
    """OCR text extraction via custom API endpoint.

    The API should accept a multipart POST with an image file
    and return JSON: {"text": "extracted text content"}
    """

    async def extract_text(
        self,
        image_path: str,
        api_base_url: str | None = None,
        api_key: str | None = None,
    ) -> str:
        """Extract text from an image using a custom OCR API.

        Sends the image as multipart/form-data to the configured endpoint.
        Expects JSON response with 'text' field.
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"图片文件不存在: {image_path}")

        if not api_base_url:
            raise ValueError("OCR API 地址未配置")

        url = api_base_url.rstrip("/")

        with open(image_path, "rb") as f:
            files = {"file": (os.path.basename(image_path), f, "image/png")}

            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            try:
                async with httpx.AsyncClient(timeout=120) as client:
                    response = await client.post(url, files=files, headers=headers)
                    response.raise_for_status()
                    data = response.json()

                    # Try common response formats
                    text = (
                        data.get("text")
                        or data.get("result")
                        or data.get("content")
                        or data.get("data", {}).get("text")
                        or ""
                    )
                    return str(text)
            except httpx.TimeoutException:
                raise RuntimeError("OCR API 请求超时 (120s)")
            except httpx.HTTPStatusError as e:
                raise RuntimeError(f"OCR API 请求失败 ({e.response.status_code}): {e.response.text[:300]}")
            except json.JSONDecodeError:
                raise RuntimeError("OCR API 返回非 JSON 格式数据")
            except Exception as e:
                raise RuntimeError(f"OCR 请求失败: {e}")

    async def extract_text_from_bytes(
        self,
        image_bytes: bytes,
        filename: str = "image.png",
        api_base_url: str | None = None,
        api_key: str | None = None,
    ) -> str:
        """Extract text from raw image bytes."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name
        try:
            return await self.extract_text(tmp_path, api_base_url, api_key)
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
