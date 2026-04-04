"""
Progress tracking using Redis for real-time updates.
"""
import asyncio
import json
import logging
from typing import Optional, Dict, Any
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

logger = logging.getLogger(__name__)


class ProgressTracker:
    """Track job progress in Redis for real-time updates."""

    def __init__(self, redis: Redis, task_id: str):
        self.redis = redis
        self.task_id = task_id
        self.key = f"progress:{task_id}"

    async def update(
        self,
        progress: int,
        message: str,
        status: str = "processing",
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Update progress in Redis.

        Args:
            progress: Progress percentage (0-100)
            message: Human-readable progress message
            status: Task status (queued, processing, completed, error)
        """
        data = {
            "task_id": self.task_id,
            "progress": progress,
            "message": message,
            "status": status,
            "metadata": metadata or {}
        }

        await self.redis.setex(
            self.key,
            3600,  # Expire after 1 hour
            json.dumps(data)
        )

        # Publish to pub/sub for real-time updates
        await self.redis.publish(
            f"progress:{self.task_id}",
            json.dumps(data)
        )

        logger.debug(f"Progress update for {self.task_id}: {progress}% - {message}")

    async def get(self) -> Optional[dict]:
        """Get current progress from Redis."""
        data = await self.redis.get(self.key)
        if data:
            return json.loads(data)
        return None

    async def complete(self, message: str = "Complete!"):
        """Mark task as completed."""
        await self.update(100, message, "completed")

    async def error(self, message: str):
        """Mark task as failed."""
        await self.update(0, message, "error")

    @staticmethod
    async def subscribe_to_progress(redis: Redis, task_id: str):
        """
        Subscribe to progress updates for a task.
        Returns an async generator that yields progress updates.
        """
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"progress:{task_id}")

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    yield data
        except (asyncio.CancelledError, GeneratorExit):
            logger.debug("Progress stream for task %s closed by client", task_id)
            raise
        finally:
            try:
                await pubsub.unsubscribe(f"progress:{task_id}")
            except RedisConnectionError:
                logger.debug(
                    "Progress stream Redis connection already closed during unsubscribe for task %s",
                    task_id,
                )
            try:
                await pubsub.close()
            except RedisConnectionError:
                logger.debug(
                    "Progress stream Redis connection already closed during pubsub close for task %s",
                    task_id,
                )
