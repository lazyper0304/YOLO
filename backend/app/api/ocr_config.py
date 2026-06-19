"""OCR config CRUD API."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_db, encrypt_api_key
from app.api import get_current_user, success_response
from app.models import OCRConfig, User
from app.exceptions import BusinessException, NotFoundException

router = APIRouter(prefix="/api/ocr-configs", tags=["ocr-configs"])


class OCRConfigCreate(BaseModel):
    name: str
    provider: str = "custom"
    api_base_url: str | None = None
    api_key: str | None = None
    language: str = "ch"
    description: str | None = None


class OCRConfigUpdate(BaseModel):
    name: str | None = None
    provider: str | None = None
    api_base_url: str | None = None
    api_key: str | None = None
    language: str | None = None
    is_active: bool | None = None
    description: str | None = None


@router.get("")
async def list_ocr_configs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OCRConfig).where(OCRConfig.user_id == current_user.id)
    )
    configs = result.scalars().all()
    return success_response(data=[
        {
            "id": c.id, "name": c.name, "provider": c.provider,
            "api_base_url": c.api_base_url,
            "language": c.language,
            "is_active": c.is_active, "description": c.description,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in configs
    ])


@router.post("")
async def create_ocr_config(
    req: OCRConfigCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    config = OCRConfig(
        user_id=current_user.id, name=req.name, provider=req.provider,
        api_base_url=req.api_base_url,
        api_key=encrypt_api_key(req.api_key) if req.api_key else None,
        language=req.language, description=req.description,
    )
    db.add(config)
    await db.flush()

    # If first config, auto-activate
    count_result = await db.execute(
        select(OCRConfig.id).where(OCRConfig.user_id == current_user.id)
    )
    count = len(count_result.scalars().all())
    if count == 1:
        config.is_active = True

    await db.commit()
    return success_response(data={"id": config.id})


@router.put("/{config_id}")
async def update_ocr_config(
    config_id: int,
    req: OCRConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OCRConfig).where(
            OCRConfig.id == config_id, OCRConfig.user_id == current_user.id
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise NotFoundException("OCR配置不存在")

    update_data = req.model_dump(exclude_unset=True)
    if not update_data:
        return success_response(data=None)

    # Encrypt api_key if provided
    if "api_key" in update_data and update_data["api_key"]:
        update_data["api_key"] = encrypt_api_key(update_data["api_key"])

    if "is_active" in update_data and update_data["is_active"]:
        # Deactivate all others first
        await db.execute(
            update(OCRConfig)
            .where(OCRConfig.user_id == current_user.id, OCRConfig.id != config_id)
            .values(is_active=False)
        )

    await db.execute(
        update(OCRConfig)
        .where(OCRConfig.id == config_id)
        .values(**update_data)
    )
    await db.commit()
    return success_response(data=None)


@router.delete("/{config_id}")
async def delete_ocr_config(
    config_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OCRConfig).where(
            OCRConfig.id == config_id, OCRConfig.user_id == current_user.id
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise NotFoundException("OCR配置不存在")

    await db.execute(delete(OCRConfig).where(OCRConfig.id == config_id))
    await db.commit()
    return success_response(data=None)
