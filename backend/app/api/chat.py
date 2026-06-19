"""Smart chat API: Q&A about detection results with streaming support."""

import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_db, get_redis, decrypt_api_key, decode_access_token
from app.models import DetectionRecord, LLMConfig
from app.api import success_response
from app.exceptions import NotFoundException, BusinessException, AuthException
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
        raise AuthException("Token required")
    payload = decode_access_token(token)
    if payload is None:
        raise AuthException("Invalid token")
    user_id = int(payload.get("sub", "0"))

    key = _history_key(user_id, task_id)
    raw = await redis.lrange(key, 0, -1)
    messages = [json.loads(m) for m in raw]
    return success_response(data={"messages": messages})


@router.post("/history")
async def save_chat_history(
    req: HistorySaveRequest,
    token: str = "",
    redis: aioredis.Redis = Depends(get_redis),
):
    """Save chat history to Redis. Auth via query ?token=."""
    if not token:
        raise AuthException("Token required")
    payload = decode_access_token(token)
    if payload is None:
        raise AuthException("Invalid token")
    user_id = int(payload.get("sub", "0"))

    key = _history_key(user_id, req.task_id)
    # Replace entire history (atomic)
    pipe = redis.pipeline()
    await pipe.delete(key)
    for msg in req.messages:
        await pipe.rpush(key, msg.model_dump_json())
    await pipe.expire(key, CHAT_HISTORY_TTL)
    await pipe.execute()
    return success_response(data=None)


@router.delete("/history")
async def clear_chat_history(
    task_id: int,
    token: str = "",
    redis: aioredis.Redis = Depends(get_redis),
):
    """Clear chat history for a given task. Auth via query ?token=."""
    if not token:
        raise AuthException("Token required")
    payload = decode_access_token(token)
    if payload is None:
        raise AuthException("Invalid token")
    user_id = int(payload.get("sub", "0"))

    key = _history_key(user_id, task_id)
    await redis.delete(key)
    return success_response(data=None)


@router.get("/stream")
async def chat_stream(
    task_id: int | None = None,
    question: str | None = None,
    token: str = "",
    llm_config_id: int | None = None,
    kb_ids: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Stream chat response via SSE. Auth via query ?token=.
    task_id is optional — if provided, context includes detection results.
    """
    # Verify token manually
    if token:
        payload = decode_access_token(token)
        if payload is None:
            raise AuthException("Invalid token")
        user_id = int(payload.get("sub", "0"))
    else:
        raise AuthException("Token required")

    if not question or not question.strip():
        raise BusinessException("问题不能为空")
    question = question.strip()

    # Build prompt
    prompt = f"用户提问：{question}\n\n请用中文回答用户问题。\n回答时请使用Markdown格式（标题、列表、加粗、代码块等），使内容层次分明、易于阅读。"

    # If task_id provided, prepend detection result context
    if task_id:
        result = await db.execute(
            select(DetectionRecord).where(
                DetectionRecord.id == task_id,
                DetectionRecord.user_id == user_id,
            )
        )
        task = result.scalar_one_or_none()
        if task is None:
            raise NotFoundException("任务不存在")
        if not task.result_json or task.status != "completed":
            raise BusinessException("任务未完成或无结果")

        # Build task context
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
            f"请基于以上检测数据用中文回答用户问题。\n"
            f"回答时请使用Markdown格式（标题、列表、加粗、代码块等），使内容层次分明、易于阅读。"
        )

    # Inject RAG context if kb_ids provided
    if kb_ids:
        try:
            parsed_kb_ids = [int(x.strip()) for x in kb_ids.split(",") if x.strip()]
            if parsed_kb_ids:
                from app.services.retrieval_service import RetrievalService
                retrieval = RetrievalService()
                search_results = await retrieval.search(
                    kb_ids=parsed_kb_ids, query=question, top_k=3
                )
                if search_results:
                    rag_context = retrieval.build_context(search_results, max_tokens=1000)
                    prompt = (
                        f"参考资料（来自知识库）:\n{rag_context}\n\n"
                        f"以下是一次目标检测的结果数据：\n\n{context}\n\n"
                        f"用户提问：{question}\n\n"
                        f"请结合参考资料和检测数据用中文回答用户问题。\n"
                        f"回答时请使用Markdown格式（标题、列表、加粗、代码块等），使内容层次分明、易于阅读。"
                    )
        except Exception:
            pass  # Ignore RAG errors, fall back to original prompt

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
        raise BusinessException("请先在模型算法管理中配置并启用一个LLM")

    try:
        api_key = decrypt_api_key(llm_config.api_key)
    except Exception as e:
        raise BusinessException(f"LLM API密钥解密失败: {e}")

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


class GeneratePromptRequest(BaseModel):
    requirement: str  # 用户自然语言描述
    llm_config_id: int | None = None
    kb_ids: str | None = None  # 逗号分隔的知识库ID


@router.post("/generate-prompt", response_model=dict)
async def generate_analysis_prompt(
    req: GeneratePromptRequest,
    token: str = "",
    db: AsyncSession = Depends(get_db),
):
    """Generate an analysis prompt for video/camera tasks via LLM conversation."""
    if not token:
        raise AuthException("Token required")
    payload = decode_access_token(token)
    if payload is None:
        raise AuthException("Invalid token")
    user_id = int(payload.get("sub", "0"))

    # Resolve LLM config
    llm_config = None
    if req.llm_config_id:
        result = await db.execute(
            select(LLMConfig).where(
                LLMConfig.id == req.llm_config_id,
                LLMConfig.user_id == user_id,
            )
        )
        llm_config = result.scalar_one_or_none()

    if llm_config is None:
        result = await db.execute(
            select(LLMConfig).where(
                LLMConfig.user_id == user_id,
                LLMConfig.is_active == True,
            )
        )
        llm_config = result.scalar_one_or_none()

    if llm_config is None:
        raise BusinessException("请先配置并启用一个LLM")

    try:
        api_key = decrypt_api_key(llm_config.api_key)
    except Exception as e:
        raise BusinessException(f"LLM API密钥解密失败: {e}")

    api_url = llm_config.api_base_url.rstrip("/")

    # Inject KB context if provided
    kb_context = ""
    if req.kb_ids:
        try:
            from app.services.retrieval_service import RetrievalService
            parsed_kb_ids = [int(x.strip()) for x in req.kb_ids.split(",") if x.strip()]
            if parsed_kb_ids:
                retrieval = RetrievalService()
                results = await retrieval.search(kb_ids=parsed_kb_ids, query=req.requirement, top_k=3)
                if results:
                    kb_context = "\n参考资料（来自知识库）：\n" + retrieval.build_context(results, max_tokens=800) + "\n"
        except Exception:
            pass  # KB errors ignored

    # Build meta-prompt for generating analysis prompts
    meta_prompt = (
        "你是一个专业的视频分析助手。用户将描述他们想要分析视频的需求，"
        "请根据用户需求生成一段结构化的视频分析提示词（prompt）。\n\n"
        "生成的提示词应该包含以下要素：\n"
        "1. 分析目标（需要从视频帧中观察和识别什么）\n"
        "2. 关键关注点（需要特别注意的细节或变化）\n"
        "3. 预期输出格式（分析结果应该包含哪些信息）\n\n"
        "要求：\n"
        "- 提示词用中文撰写\n"
        "- 长度控制在200-500字\n"
        "- 清晰、具体、可执行\n"
        "- 适合发送给多模态视觉大模型逐帧分析\n\n"
        f"用户的视频分析需求：\n{req.requirement}\n"
        f"{kb_context}\n"
        "请直接输出生成的提示词，不要添加任何前缀说明。"
    )

    try:
        import httpx

        provider = llm_config.provider.lower()
        content = ""

        if provider == "ollama" or ":11434" in api_url:
            url = f"{api_url}/api/chat"
            ollama_payload = {
                "model": llm_config.model_name,
                "messages": [{"role": "user", "content": meta_prompt}],
                "stream": False,
            }
            async with httpx.AsyncClient(timeout=httpx.Timeout(120)) as client:
                resp = await client.post(url, json=ollama_payload)
                resp.raise_for_status()
                data = resp.json()
                content = data["message"]["content"]
        else:
            url = f"{api_url}/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            openai_payload = {
                "model": llm_config.model_name,
                "messages": [{"role": "user", "content": meta_prompt}],
                "temperature": 0.7,
                "max_tokens": 1024,
            }
            async with httpx.AsyncClient(timeout=httpx.Timeout(120)) as client:
                resp = await client.post(url, headers=headers, json=openai_payload)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]

        return success_response(data={"prompt": content.strip(), "llm_model": llm_config.model_name})

    except Exception as e:
        raise BusinessException(f"生成提示词失败: {str(e)}")
