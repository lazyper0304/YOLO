"""RAG chat API — knowledge base Q&A with SSE streaming."""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import success_response
from app.core import get_db, decrypt_api_key, decode_access_token
from app.core.redis_client import get_redis
from app.exceptions import AuthException, BusinessException, NotFoundException
from app.models import User
from app.models.knowledge_base import KnowledgeBase
from app.models.llm_config import LLMConfig
from app.services.retrieval_service import RetrievalService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rag-chat", tags=["rag-chat"])

RAG_SESSION_TTL = 7 * 86400  # 7 days


def _rag_session_key(kb_id: int, session_id: str) -> str:
    return f"rag:session:{kb_id}:{session_id}"


def _rag_history_key(kb_id: int, session_id: str) -> str:
    return f"rag:history:{kb_id}:{session_id}"


def _verify_token(token: str) -> int:
    """Verify JWT token and return user_id."""
    if not token:
        raise AuthException("Token required")
    payload = decode_access_token(token)
    if payload is None:
        raise AuthException("Invalid token")
    return int(payload.get("sub", "0"))


@router.get("/stream")
async def rag_chat_stream(
    question: str,
    token: str = "",
    kb_ids: str = "",
    llm_config_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Stream RAG chat response via SSE.

    Query params:
        question: user's question
        token: JWT access token
        kb_ids: comma-separated knowledge base IDs
        llm_config_id: optional LLM config ID (uses active config if omitted)
    """
    user_id = _verify_token(token)

    # Parse KB IDs
    parsed_kb_ids = [int(x.strip()) for x in kb_ids.split(",") if x.strip().isdigit()]
    if not parsed_kb_ids:
        raise BusinessException("请选择知识库")

    # Verify KB ownership
    for kb_id in parsed_kb_ids:
        result = await db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.id == kb_id,
                KnowledgeBase.user_id == user_id,
            )
        )
        if result.scalar_one_or_none() is None:
            raise NotFoundException(f"知识库 {kb_id} 不存在")

    # Search knowledge bases
    retrieval = RetrievalService()
    try:
        search_results = await retrieval.search(
            kb_ids=parsed_kb_ids,
            query=question,
            top_k=5,
        )
    except Exception as e:
        raise BusinessException(f"知识库检索失败: {e}")

    if not search_results:
        raise BusinessException("知识库中没有找到相关内容，请上传文档后再提问")

    context = retrieval.build_context(search_results)

    # Build RAG prompt
    messages = retrieval.build_rag_prompt(question, context)

    # Get LLM config
    if llm_config_id:
        llm_result = await db.execute(
            select(LLMConfig).where(
                LLMConfig.id == llm_config_id,
                LLMConfig.user_id == user_id,
            )
        )
    else:
        llm_result = await db.execute(
            select(LLMConfig).where(
                LLMConfig.user_id == user_id,
                LLMConfig.is_active == True,
            )
        )
    llm_config = llm_result.scalar_one_or_none()
    if llm_config is None:
        raise BusinessException("请先在模型算法管理中配置并启用一个LLM")

    try:
        api_key = decrypt_api_key(llm_config.api_key)
    except Exception:
        raise BusinessException(
            "LLM API密钥解密失败，SECRET_KEY可能已变更。请在「模型算法管理」页面重新输入API密钥并保存。"
        )

    api_url = llm_config.api_base_url.rstrip("/")
    provider = llm_config.provider

    async def generate():
        import httpx

        content = ""
        reasoning_content = ""

        try:
            if provider == "ollama":
                url = f"{api_url}/chat/completions"
                payload = {
                    "model": llm_config.model_name,
                    "messages": messages,
                    "stream": True,
                }
                async with httpx.AsyncClient(timeout=120) as client:
                    async with client.stream("POST", url, json=payload) as resp:
                        resp.raise_for_status()
                        async for line in resp.aiter_lines():
                            if not line or not line.startswith("data: "):
                                continue
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue
                            choices = data.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                reasoning = delta.get("reasoning_content")
                                if reasoning:
                                    reasoning_content += reasoning
                                    yield f"event: reasoning\ndata: {json.dumps({'content': reasoning}, ensure_ascii=False)}\n\n"
                                c = delta.get("content")
                                if c:
                                    content += c
                                    yield f"data: {json.dumps({'content': c}, ensure_ascii=False)}\n\n"
            else:
                # OpenAI / custom compatible
                url = f"{api_url}/chat/completions"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": llm_config.model_name,
                    "messages": messages,
                    "stream": True,
                }
                async with httpx.AsyncClient(timeout=120) as client:
                    async with client.stream("POST", url, json=payload, headers=headers) as resp:
                        resp.raise_for_status()
                        async for line in resp.aiter_lines():
                            if not line or not line.startswith("data: "):
                                continue
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue
                            choices = data.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                reasoning = delta.get("reasoning_content")
                                if reasoning:
                                    reasoning_content += reasoning
                                    yield f"event: reasoning\ndata: {json.dumps({'content': reasoning}, ensure_ascii=False)}\n\n"
                                c = delta.get("content")
                                if c:
                                    content += c
                                    yield f"data: {json.dumps({'content': c}, ensure_ascii=False)}\n\n"

            # Signal done
            yield f"data: {json.dumps({'content': '', 'done': True, 'full_reasoning': reasoning_content}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"RAG stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': True, 'content': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─── History endpoints ────────────────────────────────────────

@router.get("/history")
async def get_rag_history(
    kb_id: int,
    session_id: str,
    token: str = "",
):
    """Get chat history for a RAG session."""
    _verify_token(token)

    redis = get_redis()
    history_key = _rag_history_key(kb_id, session_id)
    raw_messages = await redis.lrange(history_key, 0, -1)

    messages: list[dict] = []
    for raw in raw_messages:
        try:
            messages.append(json.loads(raw))
        except json.JSONDecodeError:
            pass

    return success_response(data={"session_id": session_id, "messages": messages})


@router.post("/history")
async def save_rag_history(
    request: Request,
    token: str = "",
):
    """Save messages to a RAG session's chat history."""
    _verify_token(token)

    body = await request.json()
    kb_id = int(body.get("kb_id", 0))
    session_id = body.get("session_id", "")
    messages_data = body.get("messages", [])

    if not kb_id or not session_id:
        raise BusinessException("缺少 kb_id 或 session_id")

    redis = get_redis()
    session_key = _rag_session_key(kb_id, session_id)
    history_key = _rag_history_key(kb_id, session_id)

    # Check session exists
    exists = await redis.exists(session_key)
    if not exists:
        raise NotFoundException("会话不存在")

    # Save messages
    count = 0
    for msg in messages_data:
        await redis.rpush(history_key, json.dumps(msg, ensure_ascii=False))
        count += 1

    await redis.hincrby(session_key, "message_count", count)
    await redis.hset(session_key, "updated_at", datetime.now(timezone.utc).isoformat())
    await redis.expire(session_key, RAG_SESSION_TTL)
    await redis.expire(history_key, RAG_SESSION_TTL)

    return success_response(message=f"已保存 {count} 条消息")
