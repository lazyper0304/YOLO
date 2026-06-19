"""LLM Config CRUD service."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import LLMConfig
from app.core import encrypt_api_key, decrypt_api_key
from app.exceptions import NotFoundException


def _mask_api_key(key: str) -> str:
    """Mask an API key for display: show only last 4 characters."""
    if len(key) <= 4:
        return "****"
    return "*" * (len(key) - 4) + key[-4:]


class LLMConfigService:
    """Service for CRUD operations on LLM configurations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _to_response(self, config: LLMConfig) -> dict:
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

    async def _get_user_config(self, config_id: int, user_id: int) -> LLMConfig:
        """Fetch a config by ID, ensuring it belongs to the current user."""
        result = await self.db.execute(
            select(LLMConfig).where(
                LLMConfig.id == config_id, LLMConfig.user_id == user_id
            )
        )
        config = result.scalar_one_or_none()
        if config is None:
            raise NotFoundException("LLM config not found")
        return config

    async def list_configs(self, user_id: int) -> list[dict]:
        """List all LLM configurations for the given user."""
        result = await self.db.execute(
            select(LLMConfig).where(LLMConfig.user_id == user_id)
        )
        configs = result.scalars().all()
        return [self._to_response(c) for c in configs]

    async def create_config(
        self,
        user_id: int,
        name: str,
        api_base_url: str,
        api_key: str,
        model_name: str,
        provider: str,
        is_active: bool,
    ) -> dict:
        """Create a new LLM configuration."""
        if is_active:
            active_configs = await self.db.execute(
                select(LLMConfig).where(
                    LLMConfig.user_id == user_id,
                    LLMConfig.is_active == True,
                )
            )
            for ac in active_configs.scalars().all():
                ac.is_active = False

        config = LLMConfig(
            user_id=user_id,
            name=name,
            api_base_url=api_base_url,
            api_key=encrypt_api_key(api_key),
            model_name=model_name,
            provider=provider,
            is_active=is_active,
        )
        self.db.add(config)
        await self.db.flush()
        await self.db.refresh(config)
        return self._to_response(config)

    async def get_config(self, config_id: int, user_id: int) -> dict:
        """Get a single LLM configuration by ID."""
        config = await self._get_user_config(config_id, user_id)
        return self._to_response(config)

    async def update_config(
        self, config_id: int, user_id: int, **fields
    ) -> dict:
        """Update an LLM configuration. Only provided fields are updated."""
        config = await self._get_user_config(config_id, user_id)

        if fields.get("name") is not None:
            config.name = fields["name"]
        if fields.get("api_base_url") is not None:
            config.api_base_url = fields["api_base_url"]
        if fields.get("api_key") is not None:
            config.api_key = encrypt_api_key(fields["api_key"])
        if fields.get("model_name") is not None:
            config.model_name = fields["model_name"]
        if fields.get("provider") is not None:
            config.provider = fields["provider"]
        if fields.get("is_active") is not None:
            if fields["is_active"]:
                active_configs = await self.db.execute(
                    select(LLMConfig).where(
                        LLMConfig.user_id == user_id,
                        LLMConfig.is_active == True,
                        LLMConfig.id != config_id,
                    )
                )
                for ac in active_configs.scalars().all():
                    ac.is_active = False
            config.is_active = fields["is_active"]

        await self.db.flush()
        await self.db.refresh(config)
        return self._to_response(config)

    async def delete_config(self, config_id: int, user_id: int) -> None:
        """Delete an LLM configuration."""
        config = await self._get_user_config(config_id, user_id)
        await self.db.delete(config)
        await self.db.flush()

    async def get_raw_config(self, config_id: int, user_id: int) -> LLMConfig:
        """Return the ORM object (for test endpoint which needs raw fields)."""
        return await self._get_user_config(config_id, user_id)
