"""
Source repository - handles all database operations for video sources.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class SourceRepository:
    """Repository for source-related database operations."""

    @staticmethod
    async def create_source(
        db: AsyncSession,
        source_type: str,
        title: str,
        url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a new source record and return its ID."""
        from ..models import Source

        source = Source()
        source.type = source_type
        source.title = title
        source.url = url

        db.add(source)
        await db.flush()

        source_id = source.id
        logger.info(f"Created source {source_id}: {title} ({source_type})")
        return source_id

    @staticmethod
    async def get_source_by_id(db: AsyncSession, source_id: str) -> Optional[Dict[str, Any]]:
        """Get source by ID."""
        from sqlalchemy import text

        result = await db.execute(
            text("SELECT * FROM sources WHERE id = :source_id"),
            {"source_id": source_id}
        )
        row = result.fetchone()

        if not row:
            return None

        return {
            "id": row.id,
            "type": row.type,
            "title": row.title,
            "url": getattr(row, 'url', None),
            "metadata": getattr(row, 'metadata', None),
            "created_at": row.created_at
        }

    @staticmethod
    async def update_source_title(db: AsyncSession, source_id: str, title: str) -> None:
        """Update the title of a source."""
        from sqlalchemy import text

        await db.execute(
            text("UPDATE sources SET title = :title WHERE id = :source_id"),
            {"title": title, "source_id": source_id}
        )
        await db.commit()
        logger.info(f"Updated source {source_id} title to: {title}")
