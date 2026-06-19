"""Retrieval service — semantic search and RAG context assembly with Redis caching."""

import asyncio
import hashlib
import json
import logging
import re

from app.config import settings
from app.services.chroma_service import ChromaService
from app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class RetrievalService:
    """Handles semantic search across knowledge bases and builds RAG prompts."""

    def __init__(self):
        self.chroma = ChromaService()
        self.embedder = EmbeddingService()
        self._redis = None

    def _get_redis(self):
        """Get Redis client lazily."""
        if self._redis is None:
            try:
                import redis
                self._redis = redis.Redis(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    db=2,  # Use db=2 for search cache
                    decode_responses=True,
                )
                self._redis.ping()
            except Exception as e:
                logger.warning(f"Redis connection failed, caching disabled: {e}")
                self._redis = False
        return self._redis if self._redis is not False else None

    def _get_search_cache_key(self, kb_ids: list[int], query: str, top_k: int) -> str:
        """Generate cache key for search results."""
        kb_str = ",".join(str(x) for x in sorted(kb_ids))
        query_hash = hashlib.md5(query.encode()).hexdigest()
        return f"search:{kb_str}:{query_hash}:{top_k}"

    async def search(
        self,
        kb_ids: list[int],
        query: str,
        top_k: int = 5,
    ) -> list[dict]:
        """Search across multiple knowledge bases for relevant chunks with Redis caching."""
        # Check cache
        redis = self._get_redis()
        if redis:
            try:
                cache_key = self._get_search_cache_key(kb_ids, query, top_k)
                cached = redis.get(cache_key)
                if cached:
                    logger.info("Cache hit for search query")
                    return json.loads(cached)
            except Exception:
                pass

        query_embedding = await self.embedder.embed_query(query)

        all_results = []
        for kb_id in kb_ids:
            chunks = await asyncio.get_event_loop().run_in_executor(
                None,
                self.chroma.query,
                kb_id,
                query_embedding,
                top_k,
            )
            for chunk in chunks:
                chunk["kb_id"] = kb_id
            all_results.extend(chunks)

        # Sort by distance (ascending = more similar) and take top_k
        all_results.sort(key=lambda x: x.get("distance", 999))
        results = all_results[:top_k]

        # Add highlights to each result
        for r in results:
            content = r.get("content", "")
            if content and query:
                r["highlights"] = self._extract_highlights(content, query)

        # Cache results
        if redis:
            try:
                redis.setex(cache_key, 3600, json.dumps(results, ensure_ascii=False))  # Cache for 1 hour
            except Exception:
                pass

        return results

    def build_context(
        self,
        chunks: list[dict],
        max_tokens: int | None = None,
    ) -> str:
        """Build a context string from retrieved chunks with source attribution."""
        max_tokens = max_tokens or settings.RAG_MAX_CONTEXT_TOKENS

        try:
            import tiktoken
            encoder = tiktoken.get_encoding("cl100k_base")
        except Exception:
            encoder = None

        context_parts = []
        total_tokens = 0

        for chunk in chunks:
            content = chunk.get("content", "")
            metadata = chunk.get("metadata", {})
            filename = metadata.get("filename", "未知文档")

            # Format with source attribution
            source_info = f"[来源: {filename}]"
            part = f"{source_info}\n{content}"

            # Count tokens
            if encoder:
                part_tokens = len(encoder.encode(part))
            else:
                part_tokens = len(part) // 4

            if total_tokens + part_tokens > max_tokens:
                break

            context_parts.append(part)
            total_tokens += part_tokens

        return "\n\n---\n\n".join(context_parts)

    def build_rag_prompt(
        self,
        query: str,
        context: str,
    ) -> list[dict]:
        """Build messages for LLM with RAG context injected."""
        system_msg = (
            "你是一个专业的知识库智能助手。请根据提供的参考资料回答用户问题。"
            "如果参考资料不足以回答问题，请如实说明，不要编造信息。"
            "回答时请引用相关来源文档。"
            "请使用Markdown格式组织回答：适当使用 ## 标题、**加粗**、- 列表、`行内代码`、```代码块```、以及引用 > 等语法，"
            "使回答层次分明、易于阅读。长篇回答请用小标题分段。"
        )

        user_msg = f"参考资料:\n\n{context}\n\n用户问题: {query}"

        return [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

    def _extract_highlights(
        self,
        text: str,
        query: str,
        window: int = 80,
        max_highlights: int = 3,
    ) -> list[str]:
        """Extract highlighted text fragments around query keyword matches.

        Splits text into sentences, finds those containing query keywords,
        and produces windowed fragments with <em>...</em> wrapping around matches.
        """
        if not text or not query:
            return []

        # Tokenize query: whitespace-separated terms + individual chars for Chinese
        query_tokens = [t for t in query.split() if t]
        query_chars = set(query.replace(" ", ""))

        # Split text into sentences
        sentences = re.split(r"(?<=[。！？；\n])", text)

        highlights: list[str] = []
        for sentence in sentences:
            if not sentence.strip():
                continue

            # Check if sentence contains any query token or char
            if not self._sentence_matches(sentence, query_tokens, query_chars):
                continue

            fragment = self._build_highlight_fragment(sentence, query_tokens, query_chars, window)
            if fragment:
                highlights.append(fragment)

            if len(highlights) >= max_highlights:
                break

        return highlights

    @staticmethod
    def _sentence_matches(sentence: str, tokens: list[str], chars: set) -> bool:
        """Check if a sentence contains any of the query tokens or characters."""
        lower_s = sentence.lower()
        for token in tokens:
            if token.lower() in lower_s:
                return True
        for char in chars:
            if char in sentence:
                return True
        return False

    @staticmethod
    def _build_highlight_fragment(
        sentence: str,
        tokens: list[str],
        chars: set,
        window: int,
    ) -> str:
        """Build a single highlight fragment around the first keyword match in a sentence."""
        lower_s = sentence.lower()
        first_pos = len(sentence)
        first_len = 0

        # Find the earliest keyword match
        for token in tokens:
            pos = lower_s.find(token.lower())
            if pos != -1 and pos < first_pos:
                first_pos = pos
                first_len = len(token)

        if first_pos == len(sentence):
            # No full token match found; try individual characters
            for char in chars:
                pos = sentence.find(char)
                if pos != -1 and pos < first_pos:
                    first_pos = pos
                    first_len = 1

        if first_pos == len(sentence):
            return ""  # Should not reach here if _sentence_matches passed

        # Extract window around the match
        start = max(0, first_pos - window)
        end = min(len(sentence), first_pos + first_len + window)
        fragment = sentence[start:end]

        # Add ellipsis markers for truncated text
        prefix = "…" if start > 0 else ""
        suffix = "…" if end < len(sentence) else ""

        # Wrap all keywords in <em> tags (longest-first to avoid partial matches)
        sorted_tokens = sorted(tokens, key=len, reverse=True)
        result = fragment
        for token in sorted_tokens:
            if token:
                result = re.sub(
                    re.escape(token),
                    lambda m: f"<em>{m.group()}</em>",
                    result,
                    flags=re.IGNORECASE,
                )

        return prefix + result + suffix
