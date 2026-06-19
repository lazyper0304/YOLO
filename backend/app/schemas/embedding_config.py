"""Embedding model configuration schemas."""

from pydantic import BaseModel, Field


class EmbeddingConfigCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    provider: str = Field(default="local", pattern="^(local|openai|custom)$")
    model_name: str = Field(..., min_length=1, max_length=200)
    api_base_url: str | None = None
    api_key: str | None = None
    dimension: int = Field(default=384, ge=64, le=4096)
    is_active: bool = False
    description: str | None = None


class EmbeddingConfigUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    provider: str | None = Field(None, pattern="^(local|openai|custom)$")
    model_name: str | None = Field(None, min_length=1, max_length=200)
    api_base_url: str | None = None
    api_key: str | None = None
    dimension: int | None = Field(None, ge=64, le=4096)
    is_active: bool | None = None
    description: str | None = None


class EmbeddingConfigResponse(BaseModel):
    id: int
    user_id: int
    name: str
    provider: str
    model_name: str
    api_base_url: str | None
    dimension: int
    is_active: bool
    is_default: bool
    description: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_model(cls, config) -> "EmbeddingConfigResponse":
        return cls(
            id=config.id,
            user_id=config.user_id,
            name=config.name,
            provider=config.provider,
            model_name=config.model_name,
            api_base_url=config.api_base_url,
            dimension=config.dimension,
            is_active=config.is_active,
            is_default=config.is_default,
            description=config.description,
            created_at=config.created_at.isoformat() if config.created_at else "",
            updated_at=config.updated_at.isoformat() if config.updated_at else "",
        )
