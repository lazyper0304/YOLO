"""Async Redis client wrapper."""

import redis.asyncio as aioredis
from app.config import settings

redis_client: aioredis.Redis | None = None


async def init_redis() -> aioredis.Redis:
    """Initialize and return the Redis connection pool."""
    global redis_client
    redis_client = aioredis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD or None,
        db=settings.REDIS_DB,
        decode_responses=True,
    )
    await redis_client.ping()
    return redis_client


async def close_redis() -> None:
    """Close the Redis connection."""
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None


def get_redis() -> aioredis.Redis:
    """FastAPI dependency that returns the current Redis client."""
    if redis_client is None:
        raise RuntimeError("Redis client is not initialized")
    return redis_client
