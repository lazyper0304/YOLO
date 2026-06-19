"""Deduplication service — detects and removes duplicate text chunks.

Uses normalized text comparison to find duplicates within a knowledge base.
Reduces vector storage redundancy and improves retrieval precision.
"""

import hashlib
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_base import KBChunk

logger = logging.getLogger(__name__)


def normalize_text(text: str) -> str:
    """Normalize text for comparison: lowercase, collapse whitespace, strip."""
    text = text.lower().strip()
    text = re.sub(r'\s+', ' ', text)
    return text


def content_hash(text: str) -> str:
    """Return SHA256 hex digest of normalized text."""
    return hashlib.sha256(normalize_text(text).encode('utf-8')).hexdigest()


class DedupService:
    """Detect duplicate chunks within a knowledge base."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_existing_hashes(self, knowledge_base_id: int) -> set[str]:
        """Fetch all existing chunk content hashes for a given KB."""
        result = await self.db.execute(
            select(KBChunk.content).where(
                KBChunk.knowledge_base_id == knowledge_base_id,
            )
        )
        return {content_hash(row[0]) for row in result.fetchall() if row[0]}

    async def dedup_chunks(
        self,
        chunks: list[dict[str, Any]],
        knowledge_base_id: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """Filter out duplicate chunks, returning (unique_chunks, skipped_count).

        A chunk is considered a duplicate if its normalized content hash
        matches any existing chunk in the same knowledge base.
        """
        existing = await self.get_existing_hashes(knowledge_base_id)
        if not existing:
            return chunks, 0

        unique: list[dict[str, Any]] = []
        skipped = 0
        for c in chunks:
            h = content_hash(c.get("content", ""))
            if h in existing:
                skipped += 1
            else:
                unique.append(c)
                existing.add(h)  # prevent intra-document duplicates

        if skipped > 0:
            logger.info(
                "Dedup: skipped %d / %d chunks (KB %d)",
                skipped, len(chunks), knowledge_base_id,
            )

        return unique, skipped
