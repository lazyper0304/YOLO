"""Image parser — converts image files to text descriptions via multimodal LLM."""

import base64
import logging

from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_TYPES = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff'}


class ImageParser:
    """Parse image files into text descriptions by calling a multimodal LLM."""

    ALLOWED_TYPES = ALLOWED_IMAGE_TYPES

    @classmethod
    async def parse(
        cls,
        file_path: str,
        llm_service: LLMService,
        api_base_url: str,
        api_key: str,
        model_name: str,
        provider: str = "generic",
    ) -> str:
        """Read an image file, encode as base64, and ask the LLM to describe it.

        Args:
            file_path: Absolute path to the image file.
            llm_service: An LLMService instance for making API calls.
            api_base_url: LLM API base URL.
            api_key: Decrypted API key for the LLM provider.
            model_name: Model name to use for analysis.
            provider: Provider identifier (openai/claude/ollama/generic).

        Returns:
            A text description of the image content, suitable for chunking and embedding.
        """
        img_b64 = cls._read_image_base64(file_path)
        prompt = cls._build_analysis_prompt()

        logger.info(f"Analyzing image via multimodal LLM: {file_path}")
        result = await llm_service.analyze_image(
            api_base_url=api_base_url,
            api_key=api_key,
            model_name=model_name,
            image_base64=img_b64,
            prompt=prompt,
            provider=provider,
        )

        # Prefer detailed_analysis, fall back to summary
        text = result.get("detailed_analysis", "") or result.get("summary", "")
        if not text.strip():
            logger.warning(f"LLM returned empty analysis for image: {file_path}")
            return "[图片] 无法解析图片内容"

        return text

    @classmethod
    def _read_image_base64(cls, file_path: str) -> str:
        """Read an image file and return its base64-encoded string."""
        with open(file_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')

    @classmethod
    def _build_analysis_prompt(cls) -> str:
        """Build the prompt for image analysis."""
        return (
            "请详细描述这张图片的内容，包括：\n"
            "1. 图片类型（图表、截图、照片、流程图等）\n"
            "2. 主要元素和文字内容\n"
            "3. 数据和关键信息\n"
            "4. 图片传达的核心信息\n"
            "请用中文输出，尽量详细以便后续检索。"
        )
