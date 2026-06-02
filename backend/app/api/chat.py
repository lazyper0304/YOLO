"""Smart chat API: Q&A about detection results with streaming support."""

import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis_client import get_redis
from app.models.detection_record import DetectionRecord
from app.models.llm_config import LLMConfig
from app.core.security import decrypt_api_key, decode_access_token
import redis.asyncio as aioredis

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Redis key prefix and TTL (24h = session duration)
CHAT_HISTORY_PREFIX = "chat:history"
CHAT_HISTORY_TTL = 86400  # seconds


class ChatRequest(BaseModel):
    task_id: int
    question: str
    llm_config_id: int | None = None


class HistoryMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    reasoning: str | None = None


class HistorySaveRequest(BaseModel):
    task_id: int
    messages: list[HistoryMessage]


def _history_key(user_id: int, task_id: int) -> str:
    return f"{CHAT_HISTORY_PREFIX}:{user_id}:{task_id}"


@router.get("/history")
async def get_chat_history(
    task_id: int,
    token: str = "",
    redis: aioredis.Redis = Depends(get_redis),
):
    """Load chat history from Redis for a given task. Auth via query ?token=."""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = int(payload.get("sub", "0"))

    key = _history_key(user_id, task_id)
    raw = await redis.lrange(key, 0, -1)
    messages = [json.loads(m) for m in raw]
    return {"code": 200, "data": {"messages": messages}}


@router.post("/history")
async def save_chat_history(
    req: HistorySaveRequest,
    token: str = "",
    redis: aioredis.Redis = Depends(get_redis),
):
    """Save chat history to Redis. Auth via query ?token=."""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = int(payload.get("sub", "0"))

    key = _history_key(user_id, req.task_id)
    # Replace entire history (atomic)
    pipe = redis.pipeline()
    await pipe.delete(key)
    for msg in req.messages:
        await pipe.rpush(key, msg.model_dump_json())
    await pipe.expire(key, CHAT_HISTORY_TTL)
    await pipe.execute()
    return {"code": 200, "message": "ok"}


@router.delete("/history")
async def clear_chat_history(
    task_id: int,
    token: str = "",
    redis: aioredis.Redis = Depends(get_redis),
):
    """Clear chat history for a given task. Auth via query ?token=."""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = int(payload.get("sub", "0"))

    key = _history_key(user_id, task_id)
    await redis.delete(key)
    return {"code": 200, "message": "ok"}


@router.get("/stream")
async def chat_stream(
    task_id: int,
    question: str,
    token: str = "",
    llm_config_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Stream chat response via SSE. Auth via query ?token=."""
    # Verify token manually
    if token:
        payload = decode_access_token(token)
        if payload is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        user_id = int(payload.get("sub", "0"))
    else:
        raise HTTPException(status_code=401, detail="Token required")

    # Get task
    result = await db.execute(
        select(DetectionRecord).where(
            DetectionRecord.id == task_id,
            DetectionRecord.user_id == user_id,
        )
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not task.result_json or task.status != "completed":
        raise HTTPException(status_code=400, detail="任务未完成或无结果")

    # Build context
    context_parts = [f"模式: {task.mode}"]
    bboxes = task.result_json.get("bboxes", [])
    if bboxes:
        objs = [f"{b['class_name']}({b['confidence']:.0%})" for b in bboxes]
        context_parts.append(f"检测目标: {', '.join(objs)}")
    llm_data = task.result_json.get("llm_analysis")
    if llm_data:
        if llm_data.get("summary"):
            context_parts.append(f"摘要: {llm_data['summary']}")
        if llm_data.get("detailed_analysis"):
            context_parts.append(f"详细分析: {llm_data['detailed_analysis']}")
    summary_data = task.result_json.get("detection_summary")
    if summary_data:
        parts = [f"{s['class']}({s['count']}次)" for s in summary_data]
        context_parts.append(f"视频检测汇总: {', '.join(parts)}")

    context = "\n".join(context_parts)
    prompt = (
        f"以下是一次目标检测的结果数据：\n\n{context}\n\n"
        f"用户提问：{question}\n\n"
        f"请基于以上检测数据用中文回答用户问题。"
    )

    # Get LLM config
    if llm_config_id:
        llm_result = await db.execute(
            select(LLMConfig).where(LLMConfig.id == llm_config_id, LLMConfig.user_id == user_id)
        )
    else:
        llm_result = await db.execute(
            select(LLMConfig).where(LLMConfig.user_id == user_id, LLMConfig.is_active == True)
        )
    llm_config = llm_result.scalar_one_or_none()
    if llm_config is None:
        raise HTTPException(status_code=400, detail="请先在模型算法管理中配置并启用一个LLM")

    try:
        api_key = decrypt_api_key(llm_config.api_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM API密钥解密失败: {e}")

    api_url = llm_config.api_base_url.rstrip("/")

    async def generate():
        import httpx
        content = ""
        reasoning = ""
        reasoning_done = False
        provider = llm_config.provider.lower()

        try:
            if provider == "ollama" or ":11434" in api_url:
                url = f"{api_url}/api/chat"
                payload = {
                    "model": llm_config.model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": True,
                }
                async with httpx.AsyncClient(timeout=httpx.Timeout(120)) as client:
                    async with client.stream("POST", url, json=payload) as resp:
                        async for line in resp.aiter_lines():
                            if line:
                                try:
                                    data = json.loads(line)
                                    chunk = data.get("message", {}).get("content", "")
                                    if chunk:
                                        content += chunk
                                        yield f"data: {json.dumps({'content': chunk, 'done': False})}\n\n"
                                except json.JSONDecodeError:
                                    pass
            else:
                url = f"{api_url}/chat/completions"
                payload = {
                    "model": llm_config.model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": True,
                    "temperature": 0.7,
                }
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                async with httpx.AsyncClient(timeout=httpx.Timeout(120)) as client:
                    async with client.stream("POST", url, json=payload, headers=headers) as resp:
                        async for line in resp.aiter_lines():
                            if line and line.startswith("data: "):
                                data_str = line[6:]
                                if data_str.strip() == "[DONE]":
                                    break
                                try:
                                    data = json.loads(data_str)
                                    delta = data.get("choices", [{}])[0].get("delta", {})

                                    # Reasoning content (thinking process) — e.g. DeepSeek-R1
                                    reasoning_chunk = delta.get("reasoning_content", "")
                                    if reasoning_chunk:
                                        reasoning += reasoning_chunk
                                        yield f"event: reasoning\ndata: {json.dumps({'content': reasoning_chunk, 'done': False})}\n\n"

                                    # Normal content (final answer)
                                    chunk = delta.get("content", "")
                                    if chunk:
                                        if not reasoning_done and reasoning:
                                            reasoning_done = True
                                            yield f"event: reasoning\ndata: {json.dumps({'content': '', 'done': True})}\n\n"
                                        content += chunk
                                        yield f"event: message\ndata: {json.dumps({'content': chunk, 'done': False})}\n\n"
                                except json.JSONDecodeError:
                                    pass
        except Exception as e:
            yield f"event: message\ndata: {json.dumps({'content': str(e), 'done': True, 'error': True})}\n\n"
            return

        yield f"event: message\ndata: {json.dumps({'content': '', 'done': True, 'full': content, 'full_reasoning': reasoning})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
