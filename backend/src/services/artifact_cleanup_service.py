from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Config

logger = logging.getLogger(__name__)
config = Config()

RETENTION_POLICY_HOURS = {
    "downloads": 24,
    "transcript_cache": 72,
    "waveform_cache": 72,
    "draft_previews": 72,
    "failed_task_artifacts": 168,
}


class ArtifactCleanupService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.temp_dir = Path(config.temp_dir)

    @staticmethod
    def _is_older_than(path: Path, *, max_age_hours: int) -> bool:
        try:
            modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except Exception:
            return False
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        return modified_at < cutoff

    def _collect_matching_files(self, root: Path, *, suffixes: List[str], max_age_hours: int) -> List[Path]:
        if not root.exists():
            return []
        matches: List[Path] = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if suffixes and not any(path.name.endswith(suffix) for suffix in suffixes):
                continue
            if self._is_older_than(path, max_age_hours=max_age_hours):
                matches.append(path)
        return matches

    @staticmethod
    def _delete_paths(paths: List[Path]) -> int:
        deleted = 0
        for path in paths:
            try:
                path.unlink(missing_ok=True)
                deleted += 1
            except Exception as error:
                logger.warning("Failed to delete artifact %s: %s", path, error)
        return deleted

    async def _cleanup_failed_task_clip_files(self) -> Dict[str, Any]:
        result = await self.db.execute(
            text(
                """
                SELECT gc.id, gc.file_path
                FROM generated_clips gc
                INNER JOIN tasks t ON t.id = gc.task_id
                WHERE t.status = 'error'
                  AND t.updated_at < NOW() - make_interval(hours => :max_age_hours)
                """
            ),
            {"max_age_hours": RETENTION_POLICY_HOURS["failed_task_artifacts"]},
        )
        rows = result.fetchall()
        deleted_files = 0
        deleted_clip_rows = 0
        for row in rows:
            file_path = Path(str(row.file_path))
            if file_path.exists():
                try:
                    file_path.unlink(missing_ok=True)
                    deleted_files += 1
                except Exception as error:
                    logger.warning("Failed to delete failed-task clip artifact %s: %s", file_path, error)
                    continue
            delete_result = await self.db.execute(
                text("DELETE FROM generated_clips WHERE id = :clip_id"),
                {"clip_id": row.id},
            )
            deleted_clip_rows += int(delete_result.rowcount or 0)
        await self.db.commit()
        return {
            "deleted_failed_task_files": deleted_files,
            "deleted_failed_task_clip_rows": deleted_clip_rows,
        }

    async def cleanup_expired_artifacts(self) -> Dict[str, Any]:
        downloads = self._collect_matching_files(
            self.temp_dir,
            suffixes=[".mp4", ".webm", ".mkv", ".mov"],
            max_age_hours=RETENTION_POLICY_HOURS["downloads"],
        )
        downloads = [path for path in downloads if path.parent == self.temp_dir]
        transcript_caches = self._collect_matching_files(
            self.temp_dir,
            suffixes=[".transcript_cache.json"],
            max_age_hours=RETENTION_POLICY_HOURS["transcript_cache"],
        )
        waveform_caches = self._collect_matching_files(
            self.temp_dir,
            suffixes=[".waveform_base.json"],
            max_age_hours=RETENTION_POLICY_HOURS["waveform_cache"],
        )
        draft_previews = self._collect_matching_files(
            self.temp_dir / "draft-previews",
            suffixes=[".jpg", ".jpeg"],
            max_age_hours=RETENTION_POLICY_HOURS["draft_previews"],
        )
        deleted_downloads = self._delete_paths(downloads)
        deleted_transcripts = self._delete_paths(transcript_caches)
        deleted_waveforms = self._delete_paths(waveform_caches)
        deleted_previews = self._delete_paths(draft_previews)
        failed_summary = await self._cleanup_failed_task_clip_files()
        return {
            "retention_policy_hours": dict(RETENTION_POLICY_HOURS),
            "deleted_downloads": deleted_downloads,
            "deleted_transcript_caches": deleted_transcripts,
            "deleted_waveform_caches": deleted_waveforms,
            "deleted_draft_previews": deleted_previews,
            **failed_summary,
        }
