"""Embedding service — supports API-based embedding models with Redis caching."""

import hashlib
import json
import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Embedding service using configured API models with Redis caching."""

    _instance: "EmbeddingService | None" = None
    _lock = __import__('threading').Lock()

    def __new__(cls) -> "EmbeddingService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._redis = None
        self._config_cache = None

    def _get_redis(self):
        """Get Redis client lazily."""
        if self._redis is None:
            try:
                import redis
                self._redis = redis.Redis(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    db=1,  # Use db=1 for embedding cache
                    decode_responses=True,
                )
                self._redis.ping()
            except Exception as e:
                logger.warning(f"Redis connection failed, caching disabled: {e}")
                self._redis = False
        return self._redis if self._redis is not False else None

    async def _get_config(self):
        """Get active embedding config from database."""
        if self._config_cache is not None:
            return self._config_cache

        from app.core.database import async_session_factory
        from app.models.embedding_config import EmbeddingModelConfig
        from sqlalchemy import select

        async with async_session_factory() as db:
            result = await db.execute(
                select(EmbeddingModelConfig).where(
                    EmbeddingModelConfig.is_active == True
                )
            )
            config = result.scalar_one_or_none()

            # If no active config, get default
            if config is None:
                result = await db.execute(
                    select(EmbeddingModelConfig).where(
                        EmbeddingModelConfig.is_default == True
                    )
                )
                config = result.scalar_one_or_none()

            if config is None:
                raise ValueError(
                    "未配置嵌入模型。请在「模型算法管理」页面添加并启用一个嵌入模型配置。"
                )

            raw_key = config.api_key
            if raw_key:
                from app.core import decrypt_api_key
                try:
                    raw_key = decrypt_api_key(raw_key)
                except Exception:
                    raise ValueError(
                        "嵌入模型API密钥解密失败，SECRET_KEY可能已变更。"
                        "请在「模型算法管理」页面重新输入API密钥并保存。"
                    )

            self._config_cache = {
                "provider": config.provider,
                "model_name": config.model_name,
                "api_base_url": config.api_base_url,
                "api_key": raw_key,
                "dimension": config.dimension,
            }
            return self._config_cache

    def _get_cache_key(self, text: str, model_name: str) -> str:
        """Generate cache key for text."""
        text_hash = hashlib.md5(text.encode()).hexdigest()
        return f"embedding:{model_name}:{text_hash}"

    def _get_cached_embedding(self, text: str, model_name: str) -> list[float] | None:
        """Get embedding from Redis cache."""
        redis = self._get_redis()
        if redis is None:
            return None
        try:
            key = self._get_cache_key(text, model_name)
            cached = redis.get(key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass
        return None

    def _set_cached_embedding(self, text: str, model_name: str, embedding: list[float]) -> None:
        """Save embedding to Redis cache."""
        redis = self._get_redis()
        if redis is None:
            return
        try:
            key = self._get_cache_key(text, model_name)
            redis.setex(key, 86400 * 7, json.dumps(embedding))  # Cache for 7 days
        except Exception:
            pass

    async def _call_api_embedding(self, texts: list[str], config: dict) -> list[list[float]]:
        """Call API to get embeddings. Batches in chunks of 10."""
        import httpx

        provider = config["provider"]
        api_base_url = config["api_base_url"]
        api_key = config["api_key"]
        model_name = config["model_name"]

        if not api_base_url:
            raise ValueError("API地址未配置")

        # Build request params based on provider
        if provider == "openai" or "openai" in (api_base_url or "").lower():
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            make_payload = lambda batch: {
                "model": model_name,
                "input": batch if len(batch) > 1 else batch[0],
                "encoding_format": "float",
            }
        elif "dashscope" in (api_base_url or "").lower():
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            make_payload = lambda batch: {
                "model": model_name,
                "input": batch if len(batch) > 1 else batch[0],
                "encoding_format": "float",
                "text_type": "document",
            }
        else:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            make_payload = lambda batch: {
                "model": model_name,
                "input": batch if len(batch) > 1 else batch[0],
                "encoding_format": "float",
            }

        url = f"{api_base_url.rstrip('/')}/embeddings"
        all_embeddings: list[list[float]] = []
        batch_size = 10

        async with httpx.AsyncClient(timeout=60) as client:
            for start in range(0, len(texts), batch_size):
                batch = texts[start:start + batch_size]
                payload = make_payload(batch)
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code != 200:
                    raise RuntimeError(
                        f"嵌入API请求失败 ({response.status_code}): "
                        f"{response.text[:500]}"
                    )
                data = response.json()
                items = sorted(data.get("data", []), key=lambda x: x.get("index", 0))
                for item in items:
                    all_embeddings.append(item.get("embedding", []))

        return all_embeddings

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts with Redis caching."""
        import asyncio

        # Get config
        config = await self._get_config()
        model_name = config["model_name"]

        # Check cache for each text
        results = [None] * len(texts)
        uncached_indices = []
        uncached_texts = []

        for i, text in enumerate(texts):
            cached = self._get_cached_embedding(text, model_name)
            if cached is not None:
                results[i] = cached
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        # Generate embeddings for uncached texts via API
        if uncached_texts:
            embeddings = await self._call_api_embedding(uncached_texts, config)

            # Cache results
            for idx, embedding in zip(uncached_indices, embeddings):
                results[idx] = embedding
                self._set_cached_embedding(texts[idx], model_name, embedding)

        return results

    async def embed_query(self, query: str) -> list[float]:
        """Generate embedding for a single query."""
        results = await self.embed_texts([query])
        return results[0]
