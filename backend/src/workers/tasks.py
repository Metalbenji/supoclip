"""
Worker tasks - background jobs processed by arq workers.
"""
import asyncio
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class TaskCancelledError(Exception):
    """Raised when a task is explicitly cancelled by an admin action."""


class TaskTimeoutError(Exception):
    """Raised when a task exceeds its configured timeout."""


def _resolve_task_timeout_seconds(
    transcription_options: Optional[Dict[str, Any]],
    worker_timeout_cap_seconds: int,
) -> int:
    if not isinstance(transcription_options, dict):
        return worker_timeout_cap_seconds

    raw_timeout = transcription_options.get("task_timeout_seconds")
    if raw_timeout is None:
        return worker_timeout_cap_seconds

    try:
        timeout_seconds = int(raw_timeout)
    except (TypeError, ValueError):
        logger.warning("Invalid task_timeout_seconds=%r; using worker timeout cap", raw_timeout)
        return worker_timeout_cap_seconds

    if timeout_seconds <= 0:
        logger.warning("Non-positive task_timeout_seconds=%r; using worker timeout cap", raw_timeout)
        return worker_timeout_cap_seconds

    if timeout_seconds > worker_timeout_cap_seconds:
        logger.warning(
            "task_timeout_seconds=%s exceeds worker timeout cap=%s; clamping",
            timeout_seconds,
            worker_timeout_cap_seconds,
        )
        return worker_timeout_cap_seconds

    return timeout_seconds


async def process_video_task(
    ctx: Dict[str, Any],
    task_id: str,
    url: str,
    source_type: str,
    user_id: str,
    font_family: str = "TikTokSans-Regular",
    font_size: int = 24,
    font_color: str = "#FFFFFF",
    transitions_enabled: bool = False,
    transcription_provider: str = "local",
    ai_provider: str = "openai",
    ai_model: Optional[str] = None,
    subtitle_style: Optional[Dict[str, Any]] = None,
    ai_routing_mode: Optional[str] = None,
    transcription_options: Optional[Dict[str, Any]] = None,
    render_from_drafts: bool = False,
) -> Dict[str, Any]:
    """
    Background worker task to process a video.

    Args:
        ctx: arq context (provides Redis connection and other utilities)
        task_id: Task ID to update
        url: Video URL or file path
        source_type: "youtube" or "video_url"
        user_id: User ID who created the task
        font_family: Font family for subtitles
        font_size: Font size for subtitles
        font_color: Font color for subtitles
        transitions_enabled: Whether transition effects should be applied
        transcription_provider: "local" or "assemblyai"
        ai_provider: "openai", "google", "anthropic", "zai", or "ollama"
        ai_model: Optional model override for the selected AI provider
        subtitle_style: Extra subtitle style controls for rendering
        ai_routing_mode: Optional z.ai key routing mode ("auto", "subscription", "metered")
        transcription_options: Optional local transcription overrides and task timeout
        render_from_drafts: If true, render using reviewed draft clips

    Returns:
        Dict with processing results
    """
    from ..database import AsyncSessionLocal
    from ..config import Config
    from ..services.task_service import TaskService
    from ..workers.job_queue import JobQueue
    from ..workers.progress import ProgressTracker

    logger.info(f"Worker processing task {task_id}")

    # Create progress tracker
    progress = ProgressTracker(ctx['redis'], task_id)

    async with AsyncSessionLocal() as db:
        task_service = TaskService(db)

        try:
            async def ensure_not_cancelled() -> None:
                if await JobQueue.is_task_cancelled(task_id):
                    raise TaskCancelledError("Cancelled by admin action")

            await ensure_not_cancelled()

            # Progress callback
            async def update_progress(percent: int, message: str, metadata: Optional[Dict[str, Any]] = None):
                await ensure_not_cancelled()
                await progress.update(percent, message, metadata=metadata)
                logger.info(f"Task {task_id}: {percent}% - {message}")
                await ensure_not_cancelled()

            worker_timeout_cap_seconds = int(Config().worker_job_timeout_seconds)
            task_timeout_seconds = _resolve_task_timeout_seconds(
                transcription_options=transcription_options,
                worker_timeout_cap_seconds=worker_timeout_cap_seconds,
            )

            # Process the video
            result_coro = task_service.process_task(
                task_id=task_id,
                url=url,
                source_type=source_type,
                font_family=font_family,
                font_size=font_size,
                font_color=font_color,
                transitions_enabled=transitions_enabled,
                transcription_provider=transcription_provider,
                ai_provider=ai_provider,
                ai_model=ai_model,
                ai_routing_mode=ai_routing_mode,
                transcription_options=transcription_options,
                subtitle_style=subtitle_style,
                progress_callback=update_progress,
                cancel_check=ensure_not_cancelled,
                user_id=user_id,
                render_from_drafts=render_from_drafts,
            )
            try:
                result = await asyncio.wait_for(result_coro, timeout=task_timeout_seconds)
            except asyncio.TimeoutError as exc:
                raise TaskTimeoutError(
                    f"Task exceeded timeout of {task_timeout_seconds} seconds"
                ) from exc

            final_status = str(result.get("final_status") or "completed")
            final_message = str(result.get("final_message") or "Complete!")
            final_progress = int(result.get("final_progress") or 100)
            if final_status == "completed":
                await progress.complete(final_message)
            else:
                await progress.update(
                    final_progress,
                    final_message,
                    status=final_status,
                    metadata={"phase": "analysis" if final_status == "awaiting_review" else "processing"},
                )

            logger.info("Task %s finished worker phase with status=%s", task_id, final_status)
            return result

        except TaskTimeoutError as e:
            message = str(e)
            logger.error(f"Task {task_id} timed out: {message}")
            await task_service.task_repo.update_task_status(
                db,
                task_id,
                "error",
                progress_message=message,
            )
            await progress.error(message)
            return {"task_id": task_id, "timed_out": True, "message": message}

        except TaskCancelledError as e:
            message = str(e)
            logger.info(f"Task {task_id} cancelled: {message}")
            await task_service.task_repo.update_task_status(
                db,
                task_id,
                "error",
                progress_message=message,
            )
            await progress.error(message)
            return {"task_id": task_id, "cancelled": True, "message": message}

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}", exc_info=True)
            await progress.error(str(e))
            # Error will be caught by arq and task status will be updated
            raise
        finally:
            await JobQueue.clear_task_cancelled(task_id)


# Worker configuration for arq
class WorkerSettings:
    """Configuration for arq worker."""

    from ..config import Config
    from arq.connections import RedisSettings

    config = Config()

    # Functions to run
    functions = [process_video_task]
    # Queue is configurable so dedicated worker containers can consume
    # local vs AssemblyAI jobs independently.
    queue_name = config.arq_queue_name

    # Redis settings from environment
    redis_settings = RedisSettings(
        host=config.redis_host,
        port=config.redis_port,
        database=0
    )

    # Retry settings
    max_tries = 3  # Retry failed jobs up to 3 times
    job_timeout = config.worker_job_timeout_seconds

    # Worker pool settings (local transcription is CPU-heavy).
    max_jobs = config.worker_max_jobs

    @staticmethod
    async def on_startup(ctx: Dict[str, Any]) -> None:
        from ..whisper_runtime import log_local_whisper_runtime_summary

        log_local_whisper_runtime_summary("worker_startup")


from ..whisper_runtime import log_local_whisper_runtime_summary as _log_local_whisper_runtime_summary

_log_local_whisper_runtime_summary("worker_startup_import")
