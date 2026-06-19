"""LLM Config API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_db, decrypt_api_key
from app.api import get_current_user, success_response
from app.models import User
from app.schemas.llm_config import (
    LLMConfigCreate,
    LLMConfigUpdate,
    LLMConfigResponse,
    LLMTestResponse,
)
from app.services.llm_service import LLMService
from app.services.llm_config_service import LLMConfigService

router = APIRouter(prefix="/api/llm-configs", tags=["llm-configs"])


@router.get("", response_model=dict)
async def list_configs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all LLM configurations for the current user."""
    service = LLMConfigService(db)
    return success_response(data=await service.list_configs(current_user.id))


@router.post("", response_model=dict)
async def create_config(
    req: LLMConfigCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new LLM configuration."""
    service = LLMConfigService(db)
    return success_response(data=await service.create_config(
        current_user.id, req.name, req.api_base_url, req.api_key,
        req.model_name, req.provider, req.is_active,
    ))


@router.get("/{config_id}", response_model=dict)
async def get_config(
    config_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single LLM configuration."""
    service = LLMConfigService(db)
    return success_response(data=await service.get_config(config_id, current_user.id))


@router.put("/{config_id}", response_model=dict)
async def update_config(
    config_id: int,
    req: LLMConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an LLM configuration."""
    service = LLMConfigService(db)
    return success_response(data=await service.update_config(
        config_id, current_user.id,
        name=req.name, api_base_url=req.api_base_url, api_key=req.api_key,
        model_name=req.model_name, provider=req.provider, is_active=req.is_active,
    ))


@router.delete("/{config_id}", response_model=dict)
async def delete_config(
    config_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an LLM configuration."""
    service = LLMConfigService(db)
    await service.delete_config(config_id, current_user.id)
    return success_response(data=None)


@router.post("/{config_id}/test", response_model=dict)
async def test_config(
    config_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Test an LLM configuration by sending a simple request."""
    service = LLMConfigService(db)
    config = await service.get_raw_config(config_id, current_user.id)
    llm_service = LLMService()
    result = await llm_service.test_connection(
        api_base_url=config.api_base_url,
        api_key=decrypt_api_key(config.api_key),
        model_name=config.model_name,
        provider=config.provider,
    )
    return success_response(data=result)
