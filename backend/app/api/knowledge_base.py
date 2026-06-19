"""Knowledge base API — CRUD, document management, search, and RAG Q&A."""

import asyncio
import io
import json
import logging
import os
import tempfile
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, File, UploadFile, Form
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import success_response, paginated_response
from app.api.deps import get_current_user
from app.core import get_db, decrypt_api_key
from app.core.database import async_session_factory
from app.core.redis_client import get_redis
from app.models import User, LLMConfig
from app.models.knowledge_base import KnowledgeBase, KBDocument, KBChunk
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
    KnowledgeBaseResponse,
    KBDocumentResponse,
    PaginatedDocResponse,
    KBStatsResponse,
    RAGQueryRequest,
    RAGSearchResult,
    RAGSessionCreate,
    RAGSessionResponse,
    RAGHistorySaveRequest,
    DocPreviewResponse,
    ReindexStatusResponse,
    BatchDeleteRequest,
    BatchDeleteResponse,
    ImportResultResponse,
    ImportProgressResponse,
)
from app.services.document_service import DocumentService
from app.services.retrieval_service import RetrievalService
from app.services.llm_service import LLMService
from app.exceptions import NotFoundException, BusinessException, AuthException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge-bases"])


# ─── Knowledge Base CRUD ────────────────────────────────────────────

@router.post("")
async def create_knowledge_base(
    req: KnowledgeBaseCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new knowledge base."""
    kb = KnowledgeBase(
        user_id=user.id,
        name=req.name,
        description=req.description,
        embedding_model=req.embedding_model,
    )
    db.add(kb)
    await db.flush()
    await db.refresh(kb)
    return success_response(data=KnowledgeBaseResponse.from_model(kb))


@router.get("")
async def list_knowledge_bases(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all knowledge bases for the current user."""
    result = await db.execute(
        select(KnowledgeBase)
        .where(KnowledgeBase.user_id == user.id)
        .order_by(KnowledgeBase.created_at.desc())
    )
    kbs = result.scalars().all()
    return success_response(
        data=[KnowledgeBaseResponse.from_model(kb) for kb in kbs]
    )


# ─── Search and Q&A (MUST be before /{kb_id} routes) ──────────────

@router.post("/search")
async def semantic_search(
    req: RAGQueryRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Semantic search across knowledge bases."""
    # Verify KB ownership
    for kb_id in req.kb_ids:
        result = await db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.id == kb_id,
                KnowledgeBase.user_id == user.id,
            )
        )
        if result.scalar_one_or_none() is None:
            raise NotFoundException(f"知识库不存在: {kb_id}")

    retrieval = RetrievalService()
    results = await retrieval.search(
        kb_ids=req.kb_ids,
        query=req.question,
        top_k=req.top_k,
    )

    search_results = [
        RAGSearchResult(
            chunk_id=r.get("id", ""),
            content=r.get("content", ""),
            distance=r.get("distance", 0),
            document_filename=r.get("metadata", {}).get("filename", ""),
            knowledge_base_id=r.get("kb_id", 0),
            highlights=r.get("highlights", []),
        )
        for r in results
    ]
    return success_response(data=[r.model_dump() for r in search_results])


@router.get("/ask")
async def rag_ask(
    question: str,
    kb_ids: str = "",
    token: str = "",
    llm_config_id: int | None = None,
    top_k: int = 5,
    db: AsyncSession = Depends(get_db),
):
    """RAG Q&A with streaming response (SSE). Auth via query ?token=."""
    # Verify token manually (not using HTTPBearer for SSE endpoints)
    if not token:
        raise BusinessException("Token required")
    from app.core import decode_access_token
    payload = decode_access_token(token)
    if payload is None:
        raise AuthException("Invalid token")
    user_id = int(payload.get("sub", "0"))

    # Parse kb_ids
    parsed_kb_ids = [int(x.strip()) for x in kb_ids.split(",") if x.strip()]
    if not parsed_kb_ids:
        raise BusinessException("请选择至少一个知识库")

    # Verify KB ownership
    for kb_id in parsed_kb_ids:
        result = await db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.id == kb_id,
                KnowledgeBase.user_id == user_id,
            )
        )
        if result.scalar_one_or_none() is None:
            raise NotFoundException(f"知识库不存在: {kb_id}")

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
        raise BusinessException("请先配置并启用一个LLM")

    try:
        api_key = decrypt_api_key(llm_config.api_key)
    except Exception as e:
        raise BusinessException(f"LLM API密钥解密失败: {e}")

    # Retrieve RAG context
    retrieval = RetrievalService()
    search_results = await retrieval.search(
        kb_ids=parsed_kb_ids,
        query=question,
        top_k=top_k,
    )
    context = retrieval.build_context(search_results)
    messages = retrieval.build_rag_prompt(question, context)

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
                    "messages": messages,
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
                    "messages": messages,
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

                                    reasoning_chunk = delta.get("reasoning_content", "")
                                    if reasoning_chunk:
                                        reasoning += reasoning_chunk
                                        yield f"event: reasoning\ndata: {json.dumps({'content': reasoning_chunk, 'done': False})}\n\n"

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


# ─── Knowledge Base Detail (AFTER /search and /ask) ────────────────

@router.get("/{kb_id}")
async def get_knowledge_base(
    kb_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a knowledge base by ID."""
    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == user.id,
        )
    )
    kb = result.scalar_one_or_none()
    if kb is None:
        raise NotFoundException("知识库不存在")
    return success_response(data=KnowledgeBaseResponse.from_model(kb))


@router.put("/{kb_id}")
async def update_knowledge_base(
    kb_id: int,
    req: KnowledgeBaseUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a knowledge base."""
    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == user.id,
        )
    )
    kb = result.scalar_one_or_none()
    if kb is None:
        raise NotFoundException("知识库不存在")

    if req.name is not None:
        kb.name = req.name
    if req.description is not None:
        kb.description = req.description
    if req.status is not None:
        kb.status = req.status
    await db.flush()
    await db.refresh(kb)
    return success_response(data=KnowledgeBaseResponse.from_model(kb))


@router.delete("/{kb_id}")
async def delete_knowledge_base(
    kb_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a knowledge base and all its documents/chunks."""
    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == user.id,
        )
    )
    kb = result.scalar_one_or_none()
    if kb is None:
        raise NotFoundException("知识库不存在")

    # Delete ChromaDB collection
    from app.services.chroma_service import ChromaService
    chroma = ChromaService()
    await asyncio.get_event_loop().run_in_executor(
        None, chroma.delete_collection, kb_id
    )

    await db.delete(kb)
    await db.flush()
    return success_response(message="知识库已删除")


@router.get("/{kb_id}/stats")
async def get_kb_stats(
    kb_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get knowledge base detailed statistics."""
    # Verify KB ownership
    kb_result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == user.id,
        )
    )
    if kb_result.scalar_one_or_none() is None:
        raise NotFoundException("知识库不存在")

    doc_service = DocumentService(db)
    stats = await doc_service.get_kb_stats(kb_id)
    return success_response(data=stats)


# ─── Document Management ────────────────────────────────────────────

@router.post("/{kb_id}/documents")
async def upload_document(
    kb_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document to a knowledge base."""
    content = await file.read()
    doc_service = DocumentService(db)

    try:
        doc = await doc_service.upload_document(
            user_id=user.id,
            kb_id=kb_id,
            file_content=content,
            filename=file.filename or "unnamed",
        )
    except ValueError as e:
        raise BusinessException(str(e))

    # Process synchronously so status is immediately visible to user
    try:
        await doc_service.process_document(doc.id)
    except Exception as e:
        logger.error(f"Document processing failed for doc {doc.id}: {e}", exc_info=True)
        # Failure status is already saved by process_document
        # Still return success for the upload itself
        try:
            async with async_session_factory() as refresh_db:
                result = await refresh_db.execute(
                    select(KBDocument).where(KBDocument.id == doc.id)
                )
                doc = result.scalar_one()
        except Exception:
            pass

    return success_response(data=KBDocumentResponse.from_model(doc))


@router.get("/{kb_id}/documents")
async def list_documents(
    kb_id: int,
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List documents in a knowledge base with pagination."""
    # Verify KB ownership
    kb_result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == user.id,
        )
    )
    if kb_result.scalar_one_or_none() is None:
        raise NotFoundException("知识库不存在")

    # Count total
    total_result = await db.execute(
        select(func.count(KBDocument.id)).where(KBDocument.knowledge_base_id == kb_id)
    )
    total = total_result.scalar() or 0

    # Fetch page
    offset = (page - 1) * page_size
    result = await db.execute(
        select(KBDocument)
        .where(KBDocument.knowledge_base_id == kb_id)
        .order_by(KBDocument.created_at.desc())
        .limit(page_size)
        .offset(offset)
    )
    docs = result.scalars().all()

    return paginated_response(
        items=[KBDocumentResponse.from_model(d) for d in docs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{kb_id}/documents/progress")
async def get_documents_progress(
    kb_id: int,
    doc_ids: str = "",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get Redis processing progress for multiple documents.

    Query params:
        doc_ids: comma-separated list of document IDs
    Returns:
        { "doc_id": { step, pct, message, ... }, ... }
    Documents with no Redis progress or already completed are omitted.
    """
    # Verify KB ownership
    kb_result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == user.id,
        )
    )
    if kb_result.scalar_one_or_none() is None:
        raise NotFoundException("知识库不存在")

    if not doc_ids:
        return success_response(data={})

    from app.services.kb_progress import get_progress_batch

    ids = [int(x.strip()) for x in doc_ids.split(",") if x.strip().isdigit()]
    if not ids:
        return success_response(data={})

    progress_map = await get_progress_batch(ids)
    return success_response(data=progress_map)


@router.delete("/{kb_id}/documents/{doc_id}")
async def delete_document(
    kb_id: int,
    doc_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a document from a knowledge base."""
    doc_service = DocumentService(db)
    try:
        await doc_service.delete_document(doc_id, user.id)
    except ValueError as e:
        raise NotFoundException(str(e))
    return success_response(message="文档已删除")


@router.post("/{kb_id}/documents/{doc_id}/reprocess")
async def reprocess_document(
    kb_id: int,
    doc_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-process a failed document."""
    doc_service = DocumentService(db)
    try:
        await doc_service.reprocess_document(doc_id, user.id)
    except ValueError as e:
        raise NotFoundException(str(e))

    # Process synchronously
    try:
        await doc_service.process_document(doc_id)
    except Exception as e:
        logger.error(f"Document reprocessing failed for doc {doc_id}: {e}", exc_info=True)
    return success_response(message="文档已重新处理")


# ─── Reindex ────────────────────────────────────────────────────────

@router.post("/{kb_id}/reindex")
async def trigger_reindex(
    kb_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Trigger async reindex of all non-image documents in a knowledge base.

    Only one reindex task can run per KB at a time.
    """
    # Verify KB ownership
    kb_result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == user.id,
        )
    )
    kb = kb_result.scalar_one_or_none()
    if kb is None:
        raise NotFoundException("知识库不存在")

    redis_key = f"reindex:{kb_id}"

    # Prevent concurrent reindex
    existing_status = await redis.hget(redis_key, "status")
    if existing_status in ("running", "starting"):
        raise BusinessException("该知识库正在重建索引中，请等待完成后再试")

    # Initialise Redis state
    now_iso = datetime.now(timezone.utc).isoformat()
    await redis.hset(redis_key, mapping={
        "status": "starting",
        "progress": "0",
        "processed": "0",
        "total": "0",
        "current_doc": "",
        "started_at": now_iso,
        "error_msg": "",
        "cancelled": "0",
    })

    task_id = str(uuid.uuid4())

    # Launch background reindex
    async def _reindex_background():
        try:
            doc_service = DocumentService()
            await doc_service.reindex_knowledge_base(kb_id)
        except Exception as e:
            logger.error(f"Reindex failed for KB {kb_id}: {e}", exc_info=True)
            try:
                from app.core.redis_client import redis_client
                if redis_client:
                    await redis_client.hset(redis_key, mapping={
                        "status": "failed",
                        "error_msg": str(e)[:500],
                    })
            except Exception:
                pass

    asyncio.create_task(_reindex_background())

    return success_response(data={
        "task_id": task_id,
        "status": "started",
    })


@router.get("/{kb_id}/reindex/status", response_model=ReindexStatusResponse)
async def get_reindex_status(
    kb_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Get current reindex progress for a knowledge base."""
    # Verify KB ownership
    kb_result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == user.id,
        )
    )
    if kb_result.scalar_one_or_none() is None:
        raise NotFoundException("知识库不存在")

    redis_key = f"reindex:{kb_id}"

    # Read all hash fields
    raw = await redis.hgetall(redis_key)
    if not raw:
        # No reindex record — idle
        return ReindexStatusResponse(
            kb_id=kb_id,
            status="idle",
            total_documents=0,
            processed_documents=0,
            progress_pct=0.0,
            current_document=None,
            error_message=None,
            started_at=None,
            finished_at=None,
        )

    status_val = raw.get("status", "idle")
    total_docs = int(raw.get("total", "0"))
    processed = int(raw.get("processed", "0"))
    progress_pct = float(raw.get("progress", "0"))
    current_doc = raw.get("current_doc", "") or None
    error_msg = raw.get("error_msg", "") or None
    started_at = raw.get("started_at", "") or None

    # Determine finished_at for terminal states
    finished_at_val: str | None = None
    if status_val in ("completed", "cancelled", "failed"):
        # For terminal states we treat the last update as finish time;
        # in practice the reindex method doesn't explicitly write finished_at.
        # Use started_at as a fallback — clients see status and react accordingly.
        finished_at_val = None

    return ReindexStatusResponse(
        kb_id=kb_id,
        status=status_val,
        total_documents=total_docs,
        processed_documents=processed,
        progress_pct=progress_pct,
        current_document=current_doc,
        error_message=error_msg,
        started_at=started_at,
        finished_at=finished_at_val,
    )


@router.post("/{kb_id}/reindex/cancel")
async def cancel_reindex(
    kb_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Cancel a running reindex operation for a knowledge base."""
    # Verify KB ownership
    kb_result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == user.id,
        )
    )
    if kb_result.scalar_one_or_none() is None:
        raise NotFoundException("知识库不存在")

    redis_key = f"reindex:{kb_id}"
    status_val = await redis.hget(redis_key, "status")

    if status_val not in ("running", "starting"):
        raise BusinessException("没有正在进行中的重建索引任务")

    # Set cancelled flag — background task polls this
    await redis.hset(redis_key, "cancelled", "1")
    return success_response(message="已发送取消请求，正在停止...")


# ─── RAG Chat Sessions (P1-4) ──────────────────────────────────────

RAG_SESSION_TTL = 604800  # 7 days in seconds
RAG_SESSION_PREFIX = "rag:session"
RAG_HISTORY_PREFIX = "rag:history"


def _rag_session_key(kb_id: int, session_id: str) -> str:
    """Build Redis key for a RAG session hash."""
    return f"{RAG_SESSION_PREFIX}:{kb_id}:{session_id}"


def _rag_history_key(kb_id: int, session_id: str) -> str:
    """Build Redis key for a RAG history list."""
    return f"{RAG_HISTORY_PREFIX}:{kb_id}:{session_id}"


@router.get("/{kb_id}/rag-sessions")
async def list_rag_sessions(
    kb_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all RAG chat sessions for a knowledge base."""
    # Verify KB ownership
    kb_result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == user.id,
        )
    )
    if kb_result.scalar_one_or_none() is None:
        raise NotFoundException("知识库不存在")

    redis = get_redis()
    pattern = f"{RAG_SESSION_PREFIX}:{kb_id}:*"
    sessions: list[dict] = []

    cursor = 0
    while True:
        cursor, keys = await redis.scan(cursor=cursor, match=pattern, count=100)
        for key in keys:
            data = await redis.hgetall(key)
            if data:
                sessions.append({
                    "session_id": data.get("session_id", ""),
                    "title": data.get("title", "新的对话"),
                    "message_count": int(data.get("message_count", "0")),
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                })
        if cursor == 0:
            break

    # Sort by created_at descending
    sessions.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    return success_response(data=[RAGSessionResponse(**s) for s in sessions])


@router.post("/{kb_id}/rag-sessions")
async def create_rag_session(
    kb_id: int,
    req: RAGSessionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new RAG chat session."""
    # Verify KB ownership
    kb_result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == user.id,
        )
    )
    if kb_result.scalar_one_or_none() is None:
        raise NotFoundException("知识库不存在")

    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    title = req.title or "新的对话"

    redis = get_redis()
    session_key = _rag_session_key(kb_id, session_id)
    await redis.hset(session_key, mapping={
        "session_id": session_id,
        "title": title,
        "message_count": "0",
        "created_at": now,
        "updated_at": now,
    })
    await redis.expire(session_key, RAG_SESSION_TTL)

    return success_response(data=RAGSessionResponse(
        session_id=session_id,
        title=title,
        message_count=0,
        created_at=now,
        updated_at=now,
    ))


@router.delete("/{kb_id}/rag-sessions/{session_id}")
async def delete_rag_session(
    kb_id: int,
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a RAG session and its chat history."""
    # Verify KB ownership
    kb_result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == user.id,
        )
    )
    if kb_result.scalar_one_or_none() is None:
        raise NotFoundException("知识库不存在")

    redis = get_redis()
    session_key = _rag_session_key(kb_id, session_id)
    history_key = _rag_history_key(kb_id, session_id)

    await redis.delete(session_key, history_key)
    return success_response(message="会话已删除")


@router.get("/{kb_id}/rag-sessions/{session_id}/history")
async def get_rag_history(
    kb_id: int,
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get chat history for a RAG session."""
    # Verify KB ownership
    kb_result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == user.id,
        )
    )
    if kb_result.scalar_one_or_none() is None:
        raise NotFoundException("知识库不存在")

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


@router.post("/{kb_id}/rag-sessions/{session_id}/history")
async def save_rag_history(
    kb_id: int,
    session_id: str,
    req: RAGHistorySaveRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save messages to a RAG session's chat history."""
    # Verify KB ownership
    kb_result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == user.id,
        )
    )
    if kb_result.scalar_one_or_none() is None:
        raise NotFoundException("知识库不存在")

    redis = get_redis()
    session_key = _rag_session_key(kb_id, session_id)
    history_key = _rag_history_key(kb_id, session_id)

    # Check that session exists
    exists = await redis.exists(session_key)
    if not exists:
        raise NotFoundException("会话不存在")

    # Append messages to history list
    count = 0
    for msg in req.messages:
        await redis.rpush(history_key, json.dumps(msg, ensure_ascii=False))
        count += 1

    # Update session metadata
    await redis.hincrby(session_key, "message_count", count)
    await redis.hset(session_key, "updated_at", datetime.now(timezone.utc).isoformat())
    await redis.expire(session_key, RAG_SESSION_TTL)
    await redis.expire(history_key, RAG_SESSION_TTL)

    return success_response(message=f"已保存 {count} 条消息")


@router.delete("/{kb_id}/rag-sessions/{session_id}/history")
async def clear_rag_history(
    kb_id: int,
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Clear all chat history for a RAG session."""
    # Verify KB ownership
    kb_result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == user.id,
        )
    )
    if kb_result.scalar_one_or_none() is None:
        raise NotFoundException("知识库不存在")

    redis = get_redis()
    session_key = _rag_session_key(kb_id, session_id)
    history_key = _rag_history_key(kb_id, session_id)

    await redis.delete(history_key)
    # Reset message count
    await redis.hset(session_key, "message_count", "0")
    await redis.hset(session_key, "updated_at", datetime.now(timezone.utc).isoformat())

    return success_response(message="历史记录已清空")


# ─── Document Preview (P2-1) ───────────────────────────────────────

@router.get("/{kb_id}/documents/{doc_id}/preview")
async def get_document_preview(
    kb_id: int,
    doc_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Preview a document's parsed text content."""
    # Verify KB ownership
    kb_result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == user.id,
        )
    )
    if kb_result.scalar_one_or_none() is None:
        raise NotFoundException("知识库不存在")

    doc_service = DocumentService(db)
    try:
        preview_data = await doc_service.get_document_preview(doc_id)
    except ValueError as e:
        raise NotFoundException(str(e))

    return success_response(data=preview_data)


# ─── Batch Delete (P1-6) ────────────────────────────────────────────

@router.post("/{kb_id}/documents/batch-delete")
async def batch_delete_documents(
    kb_id: int,
    req: BatchDeleteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Batch delete documents from a knowledge base.

    Each document deletion is isolated — a failure on one doc does not
    affect the others.
    """
    # Verify KB ownership
    kb_result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == user.id,
        )
    )
    if kb_result.scalar_one_or_none() is None:
        raise NotFoundException("知识库不存在")

    deleted_count = 0
    failed_doc_ids: list[int] = []

    for doc_id in req.doc_ids:
        try:
            # Use a fresh short-lived session per document to isolate failures
            async with async_session_factory() as session:
                doc_service = DocumentService(session)
                await doc_service.delete_document(doc_id, user.id)
                await session.commit()
            deleted_count += 1
        except Exception as e:
            logger.error(f"Batch delete: doc {doc_id} in KB {kb_id} failed: {e}")
            failed_doc_ids.append(doc_id)

    return success_response(data={
        "deleted_count": deleted_count,
        "failed_doc_ids": failed_doc_ids,
    })


# ─── Export (P1-7) ──────────────────────────────────────────────────

@router.get("/{kb_id}/export")
async def export_knowledge_base(
    kb_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export a knowledge base as a ZIP archive.

    The archive contains:
      - metadata.json   — KB name, description, embedding_model, created_at
      - documents.json  — list of documents with metadata
      - chunks.json     — all chunks for all documents
      - files/          — original uploaded files (if available on disk)
    """
    # Verify KB ownership
    kb_result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == user.id,
        )
    )
    kb = kb_result.scalar_one_or_none()
    if kb is None:
        raise NotFoundException("知识库不存在")

    # Fetch all documents for this KB
    doc_result = await db.execute(
        select(KBDocument)
        .where(KBDocument.knowledge_base_id == kb_id)
        .order_by(KBDocument.id)
    )
    documents = doc_result.scalars().all()

    # Fetch all chunks for all docs in this KB
    chunk_result = await db.execute(
        select(KBChunk)
        .where(KBChunk.knowledge_base_id == kb_id)
        .order_by(KBChunk.document_id, KBChunk.chunk_index)
    )
    chunks = chunk_result.scalars().all()

    # Build metadata
    metadata = {
        "name": kb.name,
        "description": kb.description,
        "embedding_model": kb.embedding_model,
        "status": kb.status,
        "document_count": kb.document_count,
        "chunk_count": kb.chunk_count,
        "created_at": kb.created_at.isoformat() if kb.created_at else "",
        "updated_at": kb.updated_at.isoformat() if kb.updated_at else "",
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }

    documents_data = [
        {
            "id": d.id,
            "filename": d.filename,
            "file_type": d.file_type,
            "file_size": d.file_size,
            "status": d.status,
            "created_at": d.created_at.isoformat() if d.created_at else "",
        }
        for d in documents
    ]

    chunks_data = [
        {
            "id": c.id,
            "document_id": c.document_id,
            "chunk_index": c.chunk_index,
            "content": c.content,
            "token_count": c.token_count,
            "metadata_json": c.metadata_json,
        }
        for c in chunks
    ]

    # Create ZIP in a temporary file
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_name = kb.name.replace(" ", "_").replace("/", "_").replace("\\", "_")
    filename = f"{safe_name}_export_{date_str}.zip"

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp_path = tmp.name
    tmp.close()

    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # Write JSON metadata files
            zf.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
            zf.writestr("documents.json", json.dumps(documents_data, ensure_ascii=False, indent=2))
            zf.writestr("chunks.json", json.dumps(chunks_data, ensure_ascii=False, indent=2))

            # Copy original files into files/ directory
            for doc in documents:
                if doc.file_path and os.path.isfile(doc.file_path):
                    arcname = f"files/{doc.filename}"
                    zf.write(doc.file_path, arcname)

        # Stream the ZIP back
        zip_file = open(tmp_path, "rb")
        file_size = os.path.getsize(tmp_path)

        async def _zip_stream():
            try:
                chunk_size = 1024 * 1024  # 1 MB chunks
                while True:
                    data = zip_file.read(chunk_size)
                    if not data:
                        break
                    yield data
            finally:
                zip_file.close()
                # Clean up temp file after streaming
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        # URL-encode filename for Content-Disposition (RFC 5987)
        from urllib.parse import quote
        encoded_filename = quote(filename)

        return StreamingResponse(
            _zip_stream(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
                "Content-Length": str(file_size),
            },
        )
    except Exception:
        # Clean up temp file on error
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ─── Import (P1-8) ──────────────────────────────────────────────────

@router.post("/{kb_id}/import")
async def import_knowledge_base(
    kb_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Import a previously exported ZIP archive into an existing knowledge base.

    Workflow:
      1. Validate ZIP and check required files
      2. Read documents.json and chunks.json
      3. Import files from files/ directory, create KBDocument records
      4. Import chunks into MySQL KBChunk table
      5. Vectorize chunks and insert into ChromaDB
      6. Update KB chunk_count
      7. Publish progress via Redis

    Returns immediately; full processing happens in background.
    """
    # Verify KB ownership
    kb_result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == user.id,
        )
    )
    kb = kb_result.scalar_one_or_none()
    if kb is None:
        raise NotFoundException("知识库不存在")

    # Read uploaded file content
    zip_content = await file.read()

    # Validate it is a ZIP file
    if not zipfile.is_zipfile(io.BytesIO(zip_content)):
        raise BusinessException("上传的文件不是有效的ZIP格式")

    # Save to temp file for zipfile processing
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp_path = tmp.name
    tmp.write(zip_content)
    tmp.close()

    # Initialise Redis progress
    redis_key = f"import:{kb_id}"
    await redis.hset(redis_key, mapping={
        "status": "starting",
        "progress_pct": "0",
        "processed_documents": "0",
        "total_documents": "0",
        "processed_chunks": "0",
        "total_chunks": "0",
        "current_step": "准备导入...",
        "error_msg": "",
    })

    # Launch background import
    async def _import_background():
        try:
            doc_service = DocumentService()
            await _do_import(kb_id, user.id, tmp_path, redis_key, doc_service)
        except Exception as e:
            logger.error(f"Import failed for KB {kb_id}: {e}", exc_info=True)
            try:
                await redis.hset(redis_key, mapping={
                    "status": "failed",
                    "error_msg": str(e)[:500],
                    "current_step": "导入失败",
                })
            except Exception:
                pass
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    asyncio.create_task(_import_background())

    return success_response(data={
        "kb_id": kb_id,
        "status": "started",
    })


async def _do_import(
    kb_id: int,
    user_id: int,
    zip_path: str,
    redis_key: str,
    doc_service: "DocumentService",
) -> None:
    """Execute the import workflow in the background.

    Reads ZIP contents and imports documents + chunks into the knowledge base.
    """
    from app.services.chroma_service import ChromaService
    from app.services.embedding_service import EmbeddingService
    from app.utils.file_utils import save_upload_file

    redis = get_redis()
    chroma = ChromaService()
    embedder = EmbeddingService()

    documents_data: list[dict] = []
    chunks_data: list[dict] = []
    file_entries: dict[str, bytes] = {}  # filename → content

    # ── Step 1: Read ZIP contents ──────────────────────────────────
    await _update_import_progress(redis, redis_key, "running", 5.0,
                                  0, 1, 0, 1, "正在读取ZIP文件...")

    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()

        # Validate required files
        if "documents.json" not in namelist:
            raise BusinessException("ZIP文件中缺少 documents.json")
        if "chunks.json" not in namelist:
            raise BusinessException("ZIP文件中缺少 chunks.json")

        # Read JSON files
        documents_data = json.loads(zf.read("documents.json").decode("utf-8"))
        chunks_data = json.loads(zf.read("chunks.json").decode("utf-8"))

        # Group chunks by document_id
        chunks_by_doc: dict[int, list[dict]] = {}
        for c in chunks_data:
            doc_id = c.get("document_id", 0)
            chunks_by_doc.setdefault(doc_id, []).append(c)

        # Read file entries
        for name in namelist:
            if name.startswith("files/") and not name.endswith("/"):
                orig_filename = name[len("files/"):]
                file_entries[orig_filename] = zf.read(name)

    total_docs = len(documents_data)
    total_chunks = len(chunks_data)

    if total_docs == 0:
        await _update_import_progress(redis, redis_key, "completed", 100.0,
                                      0, 0, 0, 0, "导入完成（无可导入的文档）")
        return

    await _update_import_progress(redis, redis_key, "running", 10.0,
                                  0, total_docs, 0, total_chunks,
                                  f"准备导入 {total_docs} 个文档...")

    # ── Step 2: Create document records ────────────────────────────
    imported_docs = 0
    imported_chunks = 0
    errors: list[str] = []
    old_to_new_doc_id: dict[int, int] = {}  # old doc id → new doc id

    for idx, doc_data in enumerate(documents_data):
        progress_pct = 10.0 + (idx / total_docs) * 30.0
        filename = doc_data.get("filename", "unknown")
        await _update_import_progress(redis, redis_key, "running", progress_pct,
                                      idx, total_docs, imported_chunks, total_chunks,
                                      f"导入文档: {filename}")

        try:
            file_content: bytes | None = None
            file_path_on_disk: str | None = None

            # Try to get file from ZIP's files/ directory
            if filename in file_entries:
                file_content = file_entries[filename]
            elif doc_data.get("file_size", 0) > 0:
                errors.append(f"文档 '{filename}' 的原始文件在ZIP中未找到，跳过")
                continue

            if file_content:
                # Save file to disk
                file_path_on_disk = await save_upload_file(
                    content=file_content,
                    original_filename=filename,
                    category="documents",
                    user_id=user_id,
                )
            else:
                # No file content — create a minimal placeholder path
                from app.config import settings
                upload_dir = Path(settings.UPLOAD_DIR)
                target_dir = upload_dir / "documents" / str(user_id)
                target_dir.mkdir(parents=True, exist_ok=True)
                file_path_on_disk = str(target_dir / f"import_{filename}")

            # Create KBDocument record
            async with async_session_factory() as session:
                doc = KBDocument(
                    knowledge_base_id=kb_id,
                    user_id=user_id,
                    filename=filename,
                    file_path=file_path_on_disk or "",
                    file_type=doc_data.get("file_type", os.path.splitext(filename)[1].lower() or ".txt"),
                    file_size=doc_data.get("file_size", len(file_content) if file_content else 0),
                    status="completed",
                )
                session.add(doc)
                await session.flush()
                await session.refresh(doc)
                new_doc_id = doc.id
                old_to_new_doc_id[doc_data["id"]] = new_doc_id

                # Import chunks for this document
                doc_chunks = chunks_by_doc.get(doc_data["id"], [])
                if doc_chunks:
                    # Create KBChunk records
                    chunk_records = []
                    for c in doc_chunks:
                        chunk = KBChunk(
                            document_id=new_doc_id,
                            knowledge_base_id=kb_id,
                            chunk_index=c.get("chunk_index", 0),
                            content=c.get("content", ""),
                            token_count=c.get("token_count", 0),
                            metadata_json=c.get("metadata_json"),
                            chroma_id=f"chunk_{new_doc_id}_{c.get('chunk_index', 0)}",
                        )
                        session.add(chunk)
                        chunk_records.append(chunk)
                    await session.flush()

                    # Generate embeddings and store in ChromaDB
                    texts = [c.get("content", "") for c in doc_chunks]
                    try:
                        embeddings = await embedder.embed_texts(texts)
                    except Exception as e:
                        logger.error(f"Import: embedding failed for doc {new_doc_id}: {e}")
                        errors.append(f"文档 '{filename}' 嵌入向量化失败: {e}")
                        # Mark document as failed
                        doc.status = "failed"
                        doc.error_message = f"嵌入向量化失败: {e}"
                        await session.flush()
                        await session.commit()
                        continue

                    chroma_ids = [cr.chroma_id for cr in chunk_records]
                    metadatas = [
                        {
                            "document_id": new_doc_id,
                            "filename": filename,
                            "chunk_index": cr.chunk_index,
                        }
                        for cr in chunk_records
                    ]
                    await asyncio.get_event_loop().run_in_executor(
                        None, chroma.add_chunks, kb_id, chroma_ids, texts, embeddings, metadatas
                    )

                    doc.chunk_count = len(doc_chunks)
                    imported_chunks += len(doc_chunks)

                await session.commit()

            imported_docs += 1

        except Exception as e:
            logger.error(f"Import: failed to import document '{filename}': {e}")
            errors.append(f"导入文档 '{filename}' 失败: {e}")

    # ── Step 3: Update KB counters ─────────────────────────────────
    await _update_import_progress(redis, redis_key, "running", 90.0,
                                  imported_docs, total_docs, imported_chunks, total_chunks,
                                  "正在更新知识库统计...")

    try:
        async with async_session_factory() as session:
            kb_result = await session.execute(
                select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
            )
            kb = kb_result.scalar_one_or_none()
            if kb:
                kb.document_count = (kb.document_count or 0) + imported_docs
                kb.chunk_count = (kb.chunk_count or 0) + imported_chunks
                await session.commit()
    except Exception as e:
        logger.error(f"Import: failed to update KB counters for KB {kb_id}: {e}")

    # ── Step 4: Mark completed ─────────────────────────────────────
    await _update_import_progress(redis, redis_key, "completed", 100.0,
                                  imported_docs, total_docs, imported_chunks, total_chunks,
                                  f"导入完成：{imported_docs} 个文档，{imported_chunks} 个片段"
                                  + (f"，{len(errors)} 个错误" if errors else ""))

    # Store errors in Redis for retrieval
    if errors:
        await redis.hset(redis_key, "errors", json.dumps(errors, ensure_ascii=False))


async def _update_import_progress(
    redis: aioredis.Redis,
    redis_key: str,
    status: str,
    progress_pct: float,
    processed_docs: int,
    total_docs: int,
    processed_chunks: int,
    total_chunks: int,
    current_step: str,
) -> None:
    """Update the import progress hash in Redis."""
    try:
        await redis.hset(redis_key, mapping={
            "status": status,
            "progress_pct": str(round(progress_pct, 1)),
            "processed_documents": str(processed_docs),
            "total_documents": str(total_docs),
            "processed_chunks": str(processed_chunks),
            "total_chunks": str(total_chunks),
            "current_step": current_step,
        })
    except Exception as e:
        logger.warning(f"Failed to update import progress: {e}")


@router.get("/{kb_id}/import/status")
async def get_import_status(
    kb_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Get the current import progress for a knowledge base."""
    # Verify KB ownership
    kb_result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == user.id,
        )
    )
    if kb_result.scalar_one_or_none() is None:
        raise NotFoundException("知识库不存在")

    redis_key = f"import:{kb_id}"
    raw = await redis.hgetall(redis_key)

    if not raw:
        return success_response(data={
            "kb_id": kb_id,
            "status": "idle",
            "progress_pct": 0.0,
            "processed_documents": 0,
            "total_documents": 0,
            "processed_chunks": 0,
            "total_chunks": 0,
            "current_step": "",
            "error_message": None,
        })

    return success_response(data={
        "kb_id": kb_id,
        "status": raw.get("status", "idle"),
        "progress_pct": float(raw.get("progress_pct", "0")),
        "processed_documents": int(raw.get("processed_documents", "0")),
        "total_documents": int(raw.get("total_documents", "0")),
        "processed_chunks": int(raw.get("processed_chunks", "0")),
        "total_chunks": int(raw.get("total_chunks", "0")),
        "current_step": raw.get("current_step", ""),
        "error_message": raw.get("error_msg", "") or None,
    })


# ─── Knowledge Graph ──────────────────────────────────────────────

@router.get("/{kb_id}/graph")
async def get_kb_graph(
    kb_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get knowledge graph (entities + relations) for visualization."""
    kb_result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == user.id)
    )
    if kb_result.scalar_one_or_none() is None:
        raise NotFoundException("知识库不存在")

    from app.services.entity_service import get_kb_graph
    graph = await get_kb_graph(kb_id)
    return success_response(data=graph)


@router.get("/{kb_id}/graph/entity/{entity_id}/chunks")
async def get_entity_chunks(
    kb_id: int,
    entity_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get document chunks related to a graph entity.

    Uses ChromaDB search with the entity name as query.
    """
    kb_result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == user.id)
    )
    if kb_result.scalar_one_or_none() is None:
        raise NotFoundException("知识库不存在")

    from app.models.knowledge_base import KBEntity
    entity = (await db.execute(select(KBEntity).where(KBEntity.id == entity_id))).scalar_one_or_none()
    if not entity:
        raise NotFoundException("实体不存在")

    # Search ChromaDB using entity name as query
    from app.services.retrieval_service import RetrievalService
    retrieval = RetrievalService()
    try:
        results = await retrieval.search(kb_ids=[kb_id], query=entity.name, top_k=5)
        return success_response(data={
            "entity": entity.name,
            "chunks": results,
        })
    except Exception as e:
        raise BusinessException(f"检索失败: {e}")


@router.post("/{kb_id}/graph/extract")
async def extract_kb_graph(
    kb_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Extract entities and relations from KB documents to build knowledge graph."""
    kb_result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == user.id)
    )
    if kb_result.scalar_one_or_none() is None:
        raise NotFoundException("知识库不存在")

    from app.services.entity_service import extract_entities_for_kb
    result = await extract_entities_for_kb(kb_id)
    return success_response(data=result)
