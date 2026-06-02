"""LLM configuration schemas."""

from pydantic import BaseModel, Field


class LLMConfigCreate(BaseModel):
    """Create a new LLM configuration."""
    name: str = Field(..., min_length=1, max_length=100)
    api_base_url: str = Field(..., min_length=1, max_length=500)
    api_key: str = Field(..., min_length=1)
    model_name: str = Field(..., min_length=1, max_length=100)
    provider: str = Field(default="generic", pattern=r"^(openai|claude|generic|ollama)$")
    is_active: bool = False


class LLMConfigUpdate(BaseModel):
    """Update an existing LLM configuration."""
    name: str | None = Field(None, min_length=1, max_length=100)
    api_base_url: str | None = Field(None, min_length=1, max_length=500)
    api_key: str | None = None
    model_name: str | None = Field(None, min_length=1, max_length=100)
    provider: str | None = Field(None, pattern=r"^(openai|claude|generic|ollama)$")
    is_active: bool | None = None


class LLMConfigResponse(BaseModel):
    """LLM configuration response (API key masked)."""
    id: int
    user_id: int
    name: str
    api_base_url: str
    api_key: str = ""  # Will be masked in response
    model_name: str
    provider: str
    is_active: bool

    class Config:
        from_attributes = True


class LLMTestResponse(BaseModel):
    """Response from testing an LLM connection."""
    success: bool
    message: str
    response_time_ms: float = 0.0
