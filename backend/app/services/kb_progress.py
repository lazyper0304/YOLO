"""Redis-backed progress tracking for knowledge base document processing."""

import json
import logging
from typing import Any

from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)

PROGRESS_KEY_PREFIX = "kb:doc:progress"
PROGRESS_TTL_SECONDS = 3600  # 1 hour, cleared on completion


def _key(doc_id: int) -> str:
    return f"{PROGRESS_KEY_PREFIX}:{doc_id}"


async def set_progress(
    doc_id: int,
    step: str,
    pct: int,
    message: str,
    extra: dict[str, Any] | None = None,
) -> None:
    """Write processing progress to Redis.

    Steps: parsing, chunking, embedding, storing, completed, failed
    """
    try:
        redis = get_redis()
        data = {
            "doc_id": doc_id,
            "step": step,
            "pct": pct,
            "message": message,
        }
        if extra:
            data.update(extra)
        await redis.setex(
            _key(doc_id),
            PROGRESS_TTL_SECONDS,
            json.dumps(data, ensure_ascii=False),
        )
    except Exception as e:
        logger.warning(f"Failed to write progress for doc {doc_id}: {e}")


async def get_progress_batch(doc_ids: list[int]) -> dict[int, dict]:
    """Read progress for multiple documents in one pipeline."""
    if not doc_ids:
        return {}
    try:
        redis = get_redis()
        pipe = redis.pipeline()
        for doc_id in doc_ids:
            pipe.get(_key(doc_id))
        results = await pipe.execute()

        progress_map = {}
        for doc_id, raw in zip(doc_ids, results):
            if raw:
                try:
                    progress_map[doc_id] = json.loads(raw)
                except json.JSONDecodeError:
                    pass
        return progress_map
    except Exception as e:
        logger.warning(f"Failed to read progress batch: {e}")
        return {}


async def delete_progress(doc_id: int) -> None:
    """Clean up progress key on completion or failure."""
    try:
        redis = get_redis()
        await redis.delete(_key(doc_id))
    except Exception as e:
        logger.warning(f"Failed to delete progress for doc {doc_id}: {e}")
