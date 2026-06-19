"""Embedding model configuration API."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import success_response
from app.api.deps import get_current_user
from app.core import get_db, encrypt_api_key
from app.models import User
from app.models.embedding_config import EmbeddingModelConfig
from app.schemas.embedding_config import (
    EmbeddingConfigCreate,
    EmbeddingConfigUpdate,
    EmbeddingConfigResponse,
)
from app.exceptions import NotFoundException, BusinessException

router = APIRouter(prefix="/api/embedding-configs", tags=["embedding-configs"])


@router.get("")
async def list_configs(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all embedding model configs for the current user."""
    result = await db.execute(
        select(EmbeddingModelConfig)
        .where(EmbeddingModelConfig.user_id == user.id)
        .order_by(EmbeddingModelConfig.created_at.desc())
    )
    configs = result.scalars().all()
    return success_response(
        data=[EmbeddingConfigResponse.from_model(c) for c in configs]
    )


@router.post("")
async def create_config(
    req: EmbeddingConfigCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new embedding model config."""
    # If setting as active, deactivate others
    if req.is_active:
        await db.execute(
            EmbeddingModelConfig.__table__.update()
            .where(EmbeddingModelConfig.user_id == user.id)
            .values(is_active=False)
        )

    config = EmbeddingModelConfig(
        user_id=user.id,
        name=req.name,
        provider=req.provider,
        model_name=req.model_name,
        api_base_url=req.api_base_url,
        api_key=encrypt_api_key(req.api_key) if req.api_key else None,
        dimension=req.dimension,
        is_active=req.is_active,
        description=req.description,
    )
    db.add(config)
    await db.flush()
    await db.refresh(config)
    return success_response(data=EmbeddingConfigResponse.from_model(config))


@router.get("/{config_id}")
async def get_config(
    config_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get an embedding model config by ID."""
    result = await db.execute(
        select(EmbeddingModelConfig).where(
            EmbeddingModelConfig.id == config_id,
            EmbeddingModelConfig.user_id == user.id,
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise NotFoundException("配置不存在")
    return success_response(data=EmbeddingConfigResponse.from_model(config))


@router.put("/{config_id}")
async def update_config(
    config_id: int,
    req: EmbeddingConfigUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an embedding model config."""
    result = await db.execute(
        select(EmbeddingModelConfig).where(
            EmbeddingModelConfig.id == config_id,
            EmbeddingModelConfig.user_id == user.id,
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise NotFoundException("配置不存在")

    # If setting as active, deactivate others
    if req.is_active:
        await db.execute(
            EmbeddingModelConfig.__table__.update()
            .where(
                EmbeddingModelConfig.user_id == user.id,
                EmbeddingModelConfig.id != config_id,
            )
            .values(is_active=False)
        )

    update_data = req.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "api_key" and value:
            value = encrypt_api_key(value)
        setattr(config, field, value)

    await db.flush()
    await db.refresh(config)
    return success_response(data=EmbeddingConfigResponse.from_model(config))


@router.delete("/{config_id}")
async def delete_config(
    config_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an embedding model config."""
    result = await db.execute(
        select(EmbeddingModelConfig).where(
            EmbeddingModelConfig.id == config_id,
            EmbeddingModelConfig.user_id == user.id,
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise NotFoundException("配置不存在")

    if config.is_default:
        raise BusinessException("不能删除默认配置")

    await db.delete(config)
    await db.flush()
    return success_response(message="配置已删除")


@router.post("/{config_id}/test")
async def test_config(
    config_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Test an embedding model config by generating a test embedding."""
    import time

    result = await db.execute(
        select(EmbeddingModelConfig).where(
            EmbeddingModelConfig.id == config_id,
            EmbeddingModelConfig.user_id == user.id,
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise NotFoundException("配置不存在")

    start = time.time()
    try:
        if config.provider == "local":
            from app.services.embedding_service import EmbeddingService
            embedder = EmbeddingService()
            import asyncio
            embedding = await asyncio.get_event_loop().run_in_executor(
                None, embedder.embed_query, "测试文本"
            )
            elapsed = (time.time() - start) * 1000
            return success_response(data={
                "success": True,
                "message": f"连接成功，向量维度: {len(embedding)}",
                "response_time_ms": round(elapsed, 2),
            })
        else:
            # For API-based embedding models
            import httpx
            from app.core import decrypt_api_key
            api_key = None
            if config.api_key:
                try:
                    api_key = decrypt_api_key(config.api_key)
                except Exception:
                    raise BusinessException("API密钥解密失败，请在编辑页面重新输入API密钥")
            if not config.api_base_url or not api_key:
                raise BusinessException("API地址和密钥不能为空")

            url = f"{config.api_base_url.rstrip('/')}/embeddings"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": config.model_name,
                "input": "测试文本",
            }
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                embedding = data.get("data", [{}])[0].get("embedding", [])
                elapsed = (time.time() - start) * 1000
                return success_response(data={
                    "success": True,
                    "message": f"连接成功，向量维度: {len(embedding)}",
                    "response_time_ms": round(elapsed, 2),
                })
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        return success_response(data={
            "success": False,
            "message": str(e),
            "response_time_ms": round(elapsed, 2),
        })
