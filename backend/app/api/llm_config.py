"""LLM Config API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decrypt_api_key
from app.api.deps import get_current_user
from app.models.user import User
from app.models.llm_config import LLMConfig
from app.schemas.llm_config import (
    LLMConfigCreate,
    LLMConfigUpdate,
    LLMConfigResponse,
    LLMTestResponse,
)
from app.services.llm_service import LLMService

router = APIRouter(prefix="/api/llm-configs", tags=["llm-configs"])


def _mask_api_key(key: str) -> str:
    """Mask an API key for display: show only last 4 characters."""
    if len(key) <= 4:
        return "****"
    return "*" * (len(key) - 4) + key[-4:]


def _to_response(config: LLMConfig) -> dict:
    """Convert an LLMConfig ORM object to a response dict (masked key)."""
    try:
        decrypted = decrypt_api_key(config.api_key)
    except Exception:
        decrypted = config.api_key
    return {
        "id": config.id,
        "user_id": config.user_id,
        "name": config.name,
        "api_base_url": config.api_base_url,
        "api_key": _mask_api_key(decrypted),
        "model_name": config.model_name,
        "provider": config.provider,
        "is_active": config.is_active,
    }


@router.get("", response_model=dict)
async def list_configs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all LLM configurations for the current user."""
    result = await db.execute(
        select(LLMConfig).where(LLMConfig.user_id == current_user.id)
    )
    configs = result.scalars().all()
    return {
        "code": 0,
        "message": "ok",
        "data": [_to_response(c) for c in configs],
    }


@router.post("", response_model=dict)
async def create_config(
    req: LLMConfigCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new LLM configuration."""
    from app.core.security import encrypt_api_key

    # If setting this config as active, deactivate others
    if req.is_active:
        active_configs = await db.execute(
            select(LLMConfig).where(
                LLMConfig.user_id == current_user.id,
                LLMConfig.is_active == True,
            )
        )
        for ac in active_configs.scalars().all():
            ac.is_active = False

    config = LLMConfig(
        user_id=current_user.id,
        name=req.name,
        api_base_url=req.api_base_url,
        api_key=encrypt_api_key(req.api_key),
        model_name=req.model_name,
        provider=req.provider,
        is_active=req.is_active,
    )
    db.add(config)
    await db.flush()
    await db.refresh(config)
    return {"code": 0, "message": "ok", "data": _to_response(config)}


@router.get("/{config_id}", response_model=dict)
async def get_config(
    config_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single LLM configuration."""
    config = await _get_user_config(config_id, current_user.id, db)
    return {"code": 0, "message": "ok", "data": _to_response(config)}


@router.put("/{config_id}", response_model=dict)
async def update_config(
    config_id: int,
    req: LLMConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an LLM configuration."""
    from app.core.security import encrypt_api_key

    config = await _get_user_config(config_id, current_user.id, db)

    if req.name is not None:
        config.name = req.name
    if req.api_base_url is not None:
        config.api_base_url = req.api_base_url
    if req.api_key is not None:
        config.api_key = encrypt_api_key(req.api_key)
    if req.model_name is not None:
        config.model_name = req.model_name
    if req.provider is not None:
        config.provider = req.provider
    if req.is_active is not None:
        if req.is_active:
            active_configs = await db.execute(
                select(LLMConfig).where(
                    LLMConfig.user_id == current_user.id,
                    LLMConfig.is_active == True,
                    LLMConfig.id != config_id,
                )
            )
            for ac in active_configs.scalars().all():
                ac.is_active = False
        config.is_active = req.is_active

    await db.flush()
    await db.refresh(config)
    return {"code": 0, "message": "ok", "data": _to_response(config)}


@router.delete("/{config_id}", response_model=dict)
async def delete_config(
    config_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an LLM configuration."""
    config = await _get_user_config(config_id, current_user.id, db)
    await db.delete(config)
    await db.flush()
    return {"code": 0, "message": "ok", "data": None}


@router.post("/{config_id}/test", response_model=dict)
async def test_config(
    config_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Test an LLM configuration by sending a simple request."""
    config = await _get_user_config(config_id, current_user.id, db)
    llm_service = LLMService()
    result = await llm_service.test_connection(
        api_base_url=config.api_base_url,
        api_key=decrypt_api_key(config.api_key),
        model_name=config.model_name,
        provider=config.provider,
    )
    return {"code": 0, "message": "ok", "data": result}


async def _get_user_config(config_id: int, user_id: int, db: AsyncSession) -> LLMConfig:
    """Fetch a config by ID, ensuring it belongs to the current user."""
    result = await db.execute(
        select(LLMConfig).where(LLMConfig.id == config_id, LLMConfig.user_id == user_id)
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LLM config not found")
    return config
