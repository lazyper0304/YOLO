"""LLM service: multi-provider adapters with automatic routing."""

import abc
import asyncio
import time
import json
from typing import Any

import httpx

from app.config import settings


class BaseLLMAdapter(abc.ABC):
    """Abstract base class for LLM provider adapters."""

    @abc.abstractmethod
    async def chat(
        self,
        api_base_url: str,
        api_key: str,
        model_name: str,
        messages: list[dict],
        timeout: int = 60,
    ) -> dict:
        """Send a chat completion request and return the response."""
        ...

    @abc.abstractmethod
    async def test_connection(
        self,
        api_base_url: str,
        api_key: str,
        model_name: str,
    ) -> dict:
        """Test the connection to the LLM provider."""
        ...


class OpenAIAdapter(BaseLLMAdapter):
    """Adapter for OpenAI-compatible API endpoints."""

    async def chat(
        self,
        api_base_url: str,
        api_key: str,
        model_name: str,
        messages: list[dict],
        timeout: int = 60,
    ) -> dict:
        url = f"{api_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 2048,
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return {
                "content": data["choices"][0]["message"]["content"],
                "model": data.get("model", model_name),
                "usage": data.get("usage", {}),
            }

    async def test_connection(
        self,
        api_base_url: str,
        api_key: str,
        model_name: str,
    ) -> dict:
        start = time.time()
        try:
            result = await self.chat(
                api_base_url=api_base_url,
                api_key=api_key,
                model_name=model_name,
                messages=[{"role": "user", "content": "Hello, respond with 'OK'."}],
                timeout=15,
            )
            elapsed = (time.time() - start) * 1000
            return {
                "success": True,
                "message": "Connection successful",
                "response_time_ms": round(elapsed, 2),
            }
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return {
                "success": False,
                "message": str(e),
                "response_time_ms": round(elapsed, 2),
            }


class ClaudeAdapter(BaseLLMAdapter):
    """Adapter for Anthropic Claude API."""

    def _convert_content_to_claude(self, content: Any) -> Any:
        """Convert OpenAI-format content blocks to Claude-compatible format.
        
        OpenAI multimodal format:
          {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
        Claude format:
          {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "..."}}
        """
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return content

        converted = []
        for block in content:
            if not isinstance(block, dict):
                converted.append(block)
                continue

            block_type = block.get("type", "")
            if block_type == "image_url":
                image_url = block.get("image_url", {})
                url = image_url.get("url", "") if isinstance(image_url, dict) else ""
                # Parse data URL: data:image/jpeg;base64,<b64data>
                if url.startswith("data:"):
                    header, b64_data = url.split(",", 1)
                    media_type = header.split(":")[1].split(";")[0]  # e.g. "image/jpeg"
                    converted.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64_data,
                        },
                    })
                else:
                    # Non-data URL, skip for safety
                    pass
            elif block_type == "text":
                converted.append({"type": "text", "text": block.get("text", "")})
            else:
                # Pass through unknown types
                converted.append(block)
        return converted

    async def chat(
        self,
        api_base_url: str,
        api_key: str,
        model_name: str,
        messages: list[dict],
        timeout: int = 60,
    ) -> dict:
        url = f"{api_base_url.rstrip('/')}/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        # Convert messages to Claude format
        system_msg = ""
        claude_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                claude_messages.append({
                    "role": msg["role"],
                    "content": self._convert_content_to_claude(msg["content"]),
                })

        payload = {
            "model": model_name,
            "messages": claude_messages,
            "max_tokens": 2048,
        }
        if system_msg:
            payload["system"] = system_msg

        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            content_blocks = data.get("content", [])
            text = " ".join(block.get("text", "") for block in content_blocks if block.get("type") == "text")
            return {
                "content": text,
                "model": data.get("model", model_name),
                "usage": data.get("usage", {}),
            }

    async def test_connection(
        self,
        api_base_url: str,
        api_key: str,
        model_name: str,
    ) -> dict:
        start = time.time()
        try:
            result = await self.chat(
                api_base_url=api_base_url,
                api_key=api_key,
                model_name=model_name,
                messages=[{"role": "user", "content": "Hello, respond with 'OK'."}],
                timeout=15,
            )
            elapsed = (time.time() - start) * 1000
            return {
                "success": True,
                "message": "Connection successful",
                "response_time_ms": round(elapsed, 2),
            }
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return {
                "success": False,
                "message": str(e),
                "response_time_ms": round(elapsed, 2),
            }


class GenericOpenAIAdapter(OpenAIAdapter):
    """Generic adapter that uses OpenAI-compatible protocol (default)."""
    pass


class OllamaAdapter(BaseLLMAdapter):
    """Adapter for Ollama native API (http://host:11434/api/chat)."""

    async def chat(
        self,
        api_base_url: str,
        api_key: str,
        model_name: str,
        messages: list[dict],
        timeout: int = 60,
    ) -> dict:
        # Ollama uses /api/chat (not /v1/chat/completions)
        url = f"{api_base_url.rstrip('/')}/api/chat"

        # Convert OpenAI-format messages to Ollama format
        ollama_messages = []
        for msg in messages:
            if isinstance(msg.get("content"), list):
                # Multimodal: extract text and images
                text_parts = []
                images = []
                for part in msg["content"]:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            text_parts.append(part["text"])
                        elif part.get("type") == "image_url":
                            url_val = part.get("image_url", {}).get("url", "")
                            if url_val.startswith("data:image/"):
                                images.append(url_val.split(",", 1)[1])
                ollama_messages.append({
                    "role": msg["role"],
                    "content": "\n".join(text_parts) if text_parts else "",
                    "images": images if images else None,
                })
            else:
                ollama_messages.append({
                    "role": msg["role"],
                    "content": str(msg["content"]),
                })

        payload = {
            "model": model_name,
            "messages": ollama_messages,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return {
                "content": data["message"]["content"],
                "model": model_name,
                "usage": {},
            }

    async def test_connection(
        self,
        api_base_url: str,
        api_key: str,
        model_name: str,
    ) -> dict:
        start = time.time()
        try:
            result = await self.chat(
                api_base_url=api_base_url,
                api_key=api_key,
                model_name=model_name,
                messages=[{"role": "user", "content": "Say OK."}],
                timeout=15,
            )
            elapsed = (time.time() - start) * 1000
            return {
                "success": True,
                "message": "Connection successful",
                "response_time_ms": round(elapsed, 2),
            }
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            msg = str(e)

            # Try to list available models for better diagnostics
            try:
                list_url = f"{api_base_url.rstrip('/')}/api/tags"
                async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as client:
                    resp = await client.get(list_url)
                    if resp.status_code == 200:
                        models = resp.json().get("models", [])
                        names = [m["name"] for m in models[:10]]
                        msg += f"\nOllama 可用模型: {', '.join(names) if names else '(无)'}"
                        msg += f"\n你请求的模型 '{model_name}' 可能未拉取，请先执行: ollama pull {model_name}"
            except Exception:
                pass

            return {
                "success": False,
                "message": msg,
                "response_time_ms": round(elapsed, 2),
            }


class LLMService:
    """LLM service with automatic adapter routing based on API base URL features."""

    # Router mapping: keyword in URL -> adapter
    ROUTER_MAP: dict[str, type[BaseLLMAdapter]] = {
        "anthropic": ClaudeAdapter,
        "claude": ClaudeAdapter,
        "openai": OpenAIAdapter,
        ":11434": OllamaAdapter,
        "ollama": OllamaAdapter,
    }

    def __init__(self):
        self._adapters: dict[str, BaseLLMAdapter] = {}

    def _get_adapter(self, api_base_url: str, provider: str = "generic") -> BaseLLMAdapter:
        """Get or create the appropriate adapter for the given provider/URL."""
        cache_key = f"{provider}:{api_base_url}"
        if cache_key in self._adapters:
            return self._adapters[cache_key]

        # Check provider hint first
        provider_lower = provider.lower()
        if provider_lower == "claude":
            adapter = ClaudeAdapter()
        elif provider_lower == "openai":
            adapter = OpenAIAdapter()
        elif provider_lower == "ollama":
            adapter = OllamaAdapter()
        else:
            # Auto-detect from URL
            for keyword, adapter_cls in self.ROUTER_MAP.items():
                if keyword in api_base_url.lower():
                    adapter = adapter_cls()
                    break
            else:
                adapter = GenericOpenAIAdapter()

        self._adapters[cache_key] = adapter
        return adapter

    async def analyze_image(
        self,
        api_base_url: str,
        api_key: str,
        model_name: str,
        image_base64: str,
        prompt: str | None = None,
        provider: str = "generic",
    ) -> dict:
        """Send an image to the LLM for analysis with the given prompt."""
        adapter = self._get_adapter(api_base_url, provider)

        if prompt is None:
            prompt = (
                "请用中文分析这张图片，描述你看到的所有对象。"
                "列出它们的名称、大致位置和详细描述。"
                "请以 JSON 格式返回，结构如下："
                '{"summary": "整体描述", '
                '"objects_detected": ["对象1", "对象2"], '
                '"detailed_analysis": "对图片的详细分析段落", '
                '"region_analyses": []}'
            )

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                    },
                ],
            }
        ]

        last_error = None
        for attempt in range(settings.LLM_MAX_RETRIES + 1):
            try:
                result = await adapter.chat(
                    api_base_url=api_base_url,
                    api_key=api_key,
                    model_name=model_name,
                    messages=messages,
                    timeout=settings.LLM_TIMEOUT_SECONDS,
                )
                # Try to parse JSON from response
                content = result.get("content", "")
                parsed = self._parse_llm_json(content)
                return parsed
            except Exception as e:
                last_error = e
                if attempt < settings.LLM_MAX_RETRIES:
                    await asyncio.sleep(1 * (attempt + 1))

        raise RuntimeError(
            f"LLM 分析失败（共尝试 {settings.LLM_MAX_RETRIES + 1} 次）\n"
            f"请检查 LLM API 地址和密钥是否正确。\n"
            f"错误详情: {last_error}"
        )

    async def analyze_region(
        self,
        api_base_url: str,
        api_key: str,
        model_name: str,
        region_base64: str,
        region_label: str,
        provider: str = "generic",
    ) -> dict:
        """Analyze a cropped region of an image."""
        prompt = (
            f"这是从一张大图中裁剪出的局部区域。该区域检测到的对象是：'{region_label}'。"
            "请用中文详细分析这个区域。描述该对象的外观、状态和任何值得注意的特征。"
            "请以 JSON 格式返回："
            '{"object": "对象名称", "description": "对该区域的详细中文分析"}'
        )
        return await self.analyze_image(
            api_base_url=api_base_url,
            api_key=api_key,
            model_name=model_name,
            image_base64=region_base64,
            prompt=prompt,
            provider=provider,
        )

    async def test_connection(
        self,
        api_base_url: str,
        api_key: str,
        model_name: str,
        provider: str = "generic",
    ) -> dict:
        """Test the connection to an LLM provider."""
        adapter = self._get_adapter(api_base_url, provider)
        return await adapter.test_connection(
            api_base_url=api_base_url,
            api_key=api_key,
            model_name=model_name,
        )

    def _parse_llm_json(self, content: str) -> dict:
        """Try to parse JSON from an LLM response. Falls back to wrapping as text."""
        # Try to find JSON block
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]

        try:
            return json.loads(content.strip())
        except json.JSONDecodeError:
            # Return as summary text without duplication
            return {
                "summary": content[:300],
                "objects_detected": [],
                "detailed_analysis": "",
                "region_analyses": [],
            }
