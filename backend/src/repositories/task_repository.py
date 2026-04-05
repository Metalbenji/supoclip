"""
Task repository - handles all database operations for tasks.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from typing import Optional, Dict, Any, List
import logging
import uuid

logger = logging.getLogger(__name__)
LLM_PROVIDER_COLUMNS = {
    "openai": "openai_api_key_encrypted",
    "google": "google_api_key_encrypted",
    "anthropic": "anthropic_api_key_encrypted",
    "zai": "zai_api_key_encrypted",
}
SUPPORTED_ZAI_KEY_PROFILES = {"subscription", "metered"}
SUPPORTED_ZAI_ROUTING_MODES = {"auto", "subscription", "metered"}
SUPPORTED_OLLAMA_AUTH_MODES = {"none", "bearer", "custom_header"}


class TaskRepository:
    """Repository for task-related database operations."""

    @staticmethod
    async def create_task(
        db: AsyncSession,
        user_id: str,
        source_id: str,
        status: str = "processing",
        font_family: str = "TikTokSans-Regular",
        font_size: int = 24,
        font_color: str = "#FFFFFF",
        subtitle_style: Optional[Dict[str, Any]] = None,
        transitions_enabled: bool = False,
        transcription_provider: str = "local",
        ai_provider: str = "openai",
        ai_focus_tags: Optional[List[str]] = None,
        review_before_render_enabled: bool = True,
        timeline_editor_enabled: bool = True,
        processing_profile: str = "balanced",
        runtime_info_json: Optional[Dict[str, Any]] = None,
        stage_checkpoint: str = "queued",
        retryable_from_stages: Optional[List[str]] = None,
    ) -> str:
        """Create a new task and return its ID."""
        result = await db.execute(
            text("""
                INSERT INTO tasks (
                    user_id,
                    source_id,
                    status,
                    font_family,
                    font_size,
                    font_color,
                    subtitle_style,
                    transitions_enabled,
                    transcription_provider,
                    ai_provider,
                    ai_focus_tags,
                    processing_profile,
                    runtime_info_json,
                    stage_checkpoint,
                    retryable_from_stages,
                    review_before_render_enabled,
                    timeline_editor_enabled,
                    created_at,
                    updated_at
                )
                VALUES (
                    :user_id,
                    :source_id,
                    :status,
                    :font_family,
                    :font_size,
                    :font_color,
                    :subtitle_style,
                    :transitions_enabled,
                    :transcription_provider,
                    :ai_provider,
                    :ai_focus_tags,
                    :processing_profile,
                    :runtime_info_json,
                    :stage_checkpoint,
                    :retryable_from_stages,
                    :review_before_render_enabled,
                    :timeline_editor_enabled,
                    NOW(),
                    NOW()
                )
                RETURNING id
            """).bindparams(
                bindparam("subtitle_style", type_=JSONB),
                bindparam("ai_focus_tags", type_=JSONB),
                bindparam("runtime_info_json", type_=JSONB),
                bindparam("retryable_from_stages", type_=JSONB),
            ),
            {
                "user_id": user_id,
                "source_id": source_id,
                "status": status,
                "font_family": font_family,
                "font_size": font_size,
                "font_color": font_color,
                "subtitle_style": subtitle_style,
                "transitions_enabled": transitions_enabled,
                "transcription_provider": transcription_provider,
                "ai_provider": ai_provider,
                "ai_focus_tags": ai_focus_tags or None,
                "processing_profile": processing_profile,
                "runtime_info_json": runtime_info_json or None,
                "stage_checkpoint": stage_checkpoint,
                "retryable_from_stages": retryable_from_stages or None,
                "review_before_render_enabled": review_before_render_enabled,
                "timeline_editor_enabled": timeline_editor_enabled,
            }
        )
        await db.commit()
        task_id = result.scalar()
        logger.info(f"Created task {task_id} for user {user_id}")
        return task_id

    @staticmethod
    async def get_task_by_id(db: AsyncSession, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task by ID with source information."""
        result = await db.execute(
            text("""
                SELECT t.*, s.title as source_title, s.type as source_type, s.url as source_url
                FROM tasks t
                LEFT JOIN sources s ON t.source_id = s.id
                WHERE t.id = :task_id
            """),
            {"task_id": task_id}
        )
        row = result.fetchone()

        if not row:
            return None

        return {
            "id": row.id,
            "user_id": row.user_id,
            "source_id": row.source_id,
            "source_title": row.source_title,
            "source_type": row.source_type,
            "source_url": getattr(row, "source_url", None),
            "status": row.status,
            "progress": getattr(row, 'progress', None),
            "progress_message": getattr(row, 'progress_message', None),
            "generated_clips_ids": row.generated_clips_ids,
            "font_family": row.font_family,
            "font_size": row.font_size,
            "font_color": row.font_color,
            "subtitle_style": getattr(row, "subtitle_style", None),
            "transitions_enabled": bool(getattr(row, "transitions_enabled", False)),
            "transcription_provider": getattr(row, "transcription_provider", "local"),
            "ai_provider": getattr(row, "ai_provider", "openai"),
            "ai_focus_tags": list(getattr(row, "ai_focus_tags", None) or []),
            "processing_profile": str(getattr(row, "processing_profile", "balanced") or "balanced"),
            "runtime_info": getattr(row, "runtime_info_json", None) or {},
            "failure_code": getattr(row, "failure_code", None),
            "failure_hint": getattr(row, "failure_hint", None),
            "stage_checkpoint": str(getattr(row, "stage_checkpoint", "queued") or "queued"),
            "retryable_from_stages": list(getattr(row, "retryable_from_stages", None) or []),
            "review_before_render_enabled": bool(getattr(row, "review_before_render_enabled", True)),
            "timeline_editor_enabled": bool(getattr(row, "timeline_editor_enabled", True)),
            "created_at": row.created_at,
            "updated_at": row.updated_at
        }

    @staticmethod
    async def get_tasks_for_subtitle_style_backfill(
        db: AsyncSession,
        statuses: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        task_ids: Optional[List[str]] = None,
        include_existing: bool = False,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch tasks plus user default style fields used to reconstruct subtitle_style.
        """
        where_clauses: List[str] = []
        params: Dict[str, Any] = {}

        if statuses is None:
            normalized_statuses = ["awaiting_review"]
        else:
            normalized_statuses = [status.strip() for status in statuses if status and status.strip()]
        if normalized_statuses:
            where_clauses.append("t.status = ANY(:statuses)")
            params["statuses"] = normalized_statuses

        if user_id:
            where_clauses.append("t.user_id = :user_id")
            params["user_id"] = user_id

        normalized_task_ids = [task_id.strip() for task_id in (task_ids or []) if isinstance(task_id, str) and task_id.strip()]
        if normalized_task_ids:
            where_clauses.append("t.id = ANY(:task_ids)")
            params["task_ids"] = normalized_task_ids

        if not include_existing:
            where_clauses.append("t.subtitle_style IS NULL")

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        limit_sql = ""
        if limit is not None:
            limit_sql = "LIMIT :limit"
            params["limit"] = max(1, int(limit))

        result = await db.execute(
            text(
                f"""
                SELECT
                    t.id,
                    t.user_id,
                    t.status,
                    t.font_family,
                    t.font_size,
                    t.font_color,
                    t.subtitle_style,
                    u.default_font_weight,
                    u.default_highlight_color,
                    u.default_line_height,
                    u.default_letter_spacing,
                    u.default_text_transform,
                    u.default_text_align,
                    u.default_stroke_color,
                    u.default_stroke_width,
                    u.default_stroke_blur,
                    u.default_shadow_color,
                    u.default_shadow_opacity,
                    u.default_shadow_blur,
                    u.default_shadow_offset_x,
                    u.default_shadow_offset_y
                FROM tasks t
                INNER JOIN users u ON u.id = t.user_id
                {where_sql}
                ORDER BY t.created_at ASC
                {limit_sql}
                """
            ),
            params,
        )

        tasks: List[Dict[str, Any]] = []
        for row in result.fetchall():
            tasks.append(
                {
                    "id": row.id,
                    "user_id": row.user_id,
                    "status": row.status,
                    "font_family": row.font_family,
                    "font_size": row.font_size,
                    "font_color": row.font_color,
                    "subtitle_style": getattr(row, "subtitle_style", None),
                    "default_font_weight": getattr(row, "default_font_weight", None),
                    "default_highlight_color": getattr(row, "default_highlight_color", None),
                    "default_line_height": getattr(row, "default_line_height", None),
                    "default_letter_spacing": getattr(row, "default_letter_spacing", None),
                    "default_text_transform": getattr(row, "default_text_transform", None),
                    "default_text_align": getattr(row, "default_text_align", None),
                    "default_stroke_color": getattr(row, "default_stroke_color", None),
                    "default_stroke_width": getattr(row, "default_stroke_width", None),
                    "default_stroke_blur": getattr(row, "default_stroke_blur", None),
                    "default_shadow_color": getattr(row, "default_shadow_color", None),
                    "default_shadow_opacity": getattr(row, "default_shadow_opacity", None),
                    "default_shadow_blur": getattr(row, "default_shadow_blur", None),
                    "default_shadow_offset_x": getattr(row, "default_shadow_offset_x", None),
                    "default_shadow_offset_y": getattr(row, "default_shadow_offset_y", None),
                }
            )
        return tasks

    @staticmethod
    async def update_task_subtitle_style(
        db: AsyncSession,
        task_id: str,
        subtitle_style: Dict[str, Any],
    ) -> bool:
        """
        Persist normalized subtitle style and keep top-level font fields in sync.
        """
        result = await db.execute(
            text(
                """
                UPDATE tasks
                SET
                    subtitle_style = :subtitle_style,
                    font_family = :font_family,
                    font_size = :font_size,
                    font_color = :font_color,
                    updated_at = NOW()
                WHERE id = :task_id
                """
            ).bindparams(bindparam("subtitle_style", type_=JSONB)),
            {
                "task_id": task_id,
                "subtitle_style": subtitle_style,
                "font_family": subtitle_style.get("font_family"),
                "font_size": subtitle_style.get("font_size"),
                "font_color": subtitle_style.get("font_color"),
            },
        )
        await db.commit()
        return (result.rowcount or 0) > 0

    @staticmethod
    async def update_task_subtitle_styles_bulk(
        db: AsyncSession,
        styles_by_task_id: Dict[str, Dict[str, Any]],
    ) -> int:
        """
        Bulk variant of update_task_subtitle_style.
        Returns count of tasks updated.
        """
        updated_count = 0
        for task_id, subtitle_style in styles_by_task_id.items():
            result = await db.execute(
                text(
                    """
                    UPDATE tasks
                    SET
                        subtitle_style = :subtitle_style,
                        font_family = :font_family,
                        font_size = :font_size,
                        font_color = :font_color,
                        updated_at = NOW()
                    WHERE id = :task_id
                    """
                ).bindparams(bindparam("subtitle_style", type_=JSONB)),
                {
                    "task_id": task_id,
                    "subtitle_style": subtitle_style,
                    "font_family": subtitle_style.get("font_family"),
                    "font_size": subtitle_style.get("font_size"),
                    "font_color": subtitle_style.get("font_color"),
                },
            )
            if (result.rowcount or 0) > 0:
                updated_count += 1
        await db.commit()
        return updated_count

    @staticmethod
    async def update_task_status(
        db: AsyncSession,
        task_id: str,
        status: str,
        progress: Optional[int] = None,
        progress_message: Optional[str] = None,
        runtime_info: Optional[Dict[str, Any]] = None,
        failure_code: Optional[str] = None,
        failure_hint: Optional[str] = None,
        stage_checkpoint: Optional[str] = None,
        retryable_from_stages: Optional[List[str]] = None,
        clear_failure: bool = False,
    ) -> None:
        """Update task status and optional progress."""
        params = {
            "task_id": task_id,
            "status": status,
            "progress": progress,
            "progress_message": progress_message,
            "runtime_info": runtime_info,
            "failure_code": failure_code,
            "failure_hint": failure_hint,
            "stage_checkpoint": stage_checkpoint,
            "retryable_from_stages": retryable_from_stages,
        }

        # Build SET clauses dynamically, then append WHERE separately.
        set_clauses = ["status = :status"]

        if progress is not None:
            set_clauses.append("progress = :progress")

        if progress_message is not None:
            set_clauses.append("progress_message = :progress_message")

        if runtime_info is not None:
            set_clauses.append("runtime_info_json = :runtime_info")

        if stage_checkpoint is not None:
            set_clauses.append("stage_checkpoint = :stage_checkpoint")

        if retryable_from_stages is not None:
            set_clauses.append("retryable_from_stages = :retryable_from_stages")

        if clear_failure:
            set_clauses.append("failure_code = NULL")
            set_clauses.append("failure_hint = NULL")
        else:
            if failure_code is not None:
                set_clauses.append("failure_code = :failure_code")
            if failure_hint is not None:
                set_clauses.append("failure_hint = :failure_hint")

        set_clauses.append("updated_at = NOW()")

        query = f"UPDATE tasks SET {', '.join(set_clauses)} WHERE id = :task_id"

        statement = text(query)
        bind_params = []
        if runtime_info is not None:
            bind_params.append(bindparam("runtime_info", type_=JSONB))
        if retryable_from_stages is not None:
            bind_params.append(bindparam("retryable_from_stages", type_=JSONB))
        if bind_params:
            statement = statement.bindparams(*bind_params)

        await db.execute(statement, params)
        await db.commit()
        logger.info(f"Updated task {task_id} status to {status}" +
                   (f" (progress: {progress}%)" if progress else ""))

    @staticmethod
    async def update_task_clips(db: AsyncSession, task_id: str, clip_ids: List[str]) -> None:
        """Update task with generated clip IDs."""
        await db.execute(
            text("UPDATE tasks SET generated_clips_ids = :clip_ids, updated_at = NOW() WHERE id = :task_id"),
            {"clip_ids": clip_ids, "task_id": task_id}
        )
        await db.commit()
        logger.info(f"Updated task {task_id} with {len(clip_ids)} clips")

    @staticmethod
    async def get_user_tasks(db: AsyncSession, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get all tasks for a user."""
        result = await db.execute(
            text("""
                SELECT t.*, s.title as source_title, s.type as source_type, s.url as source_url,
                       (SELECT COUNT(*) FROM generated_clips WHERE task_id = t.id) as clips_count
                FROM tasks t
                LEFT JOIN sources s ON t.source_id = s.id
                WHERE t.user_id = :user_id
                ORDER BY t.created_at DESC
                LIMIT :limit
            """),
            {"user_id": user_id, "limit": limit}
        )

        tasks = []
        for row in result.fetchall():
            tasks.append({
                "id": row.id,
                "user_id": row.user_id,
                "source_id": row.source_id,
                "source_title": row.source_title,
                "source_type": row.source_type,
                "source_url": getattr(row, "source_url", None),
                "status": row.status,
                "transitions_enabled": bool(getattr(row, "transitions_enabled", False)),
                "transcription_provider": getattr(row, "transcription_provider", "local"),
                "ai_provider": getattr(row, "ai_provider", "openai"),
                "ai_focus_tags": list(getattr(row, "ai_focus_tags", None) or []),
                "processing_profile": str(getattr(row, "processing_profile", "balanced") or "balanced"),
                "runtime_info": getattr(row, "runtime_info_json", None) or {},
                "failure_code": getattr(row, "failure_code", None),
                "failure_hint": getattr(row, "failure_hint", None),
                "stage_checkpoint": str(getattr(row, "stage_checkpoint", "queued") or "queued"),
                "retryable_from_stages": list(getattr(row, "retryable_from_stages", None) or []),
                "progress": getattr(row, "progress", None),
                "progress_message": getattr(row, "progress_message", None),
                "review_before_render_enabled": bool(getattr(row, "review_before_render_enabled", True)),
                "timeline_editor_enabled": bool(getattr(row, "timeline_editor_enabled", True)),
                "clips_count": row.clips_count,
                "created_at": row.created_at,
                "updated_at": row.updated_at
            })

        return tasks

    @staticmethod
    async def get_user_encrypted_assembly_key(db: AsyncSession, user_id: str) -> Optional[str]:
        """Get encrypted AssemblyAI key for a user."""
        result = await db.execute(
            text("SELECT assembly_api_key_encrypted FROM users WHERE id = :user_id"),
            {"user_id": user_id},
        )
        row = result.fetchone()
        if not row:
            return None
        return row.assembly_api_key_encrypted

    @staticmethod
    async def get_user_youtube_cookies(db: AsyncSession, user_id: str) -> Optional[Dict[str, Any]]:
        """Get encrypted YouTube cookies metadata for a user."""
        result = await db.execute(
            text(
                """
                SELECT
                    youtube_cookies_encrypted,
                    youtube_cookies_filename,
                    youtube_cookies_updated_at
                FROM users
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id},
        )
        row = result.fetchone()
        if not row or not getattr(row, "youtube_cookies_encrypted", None):
            return None
        return {
            "encrypted_value": row.youtube_cookies_encrypted,
            "filename": getattr(row, "youtube_cookies_filename", None),
            "updated_at": getattr(row, "youtube_cookies_updated_at", None),
        }

    @staticmethod
    async def get_user_encrypted_ai_key(
        db: AsyncSession,
        user_id: str,
        provider: str,
    ) -> Optional[str]:
        """Get encrypted LLM provider API key for a user."""
        column = LLM_PROVIDER_COLUMNS.get(provider)
        if not column:
            raise ValueError(f"Unsupported AI provider: {provider}")
        result = await db.execute(
            text(f"SELECT {column} FROM users WHERE id = :user_id"),
            {"user_id": user_id},
        )
        row = result.fetchone()
        if not row:
            return None
        return getattr(row, column)

    @staticmethod
    async def set_user_encrypted_assembly_key(
        db: AsyncSession,
        user_id: str,
        encrypted_key: str,
    ) -> None:
        """Store encrypted AssemblyAI key for a user."""
        result = await db.execute(
            text(
                """
                UPDATE users
                SET assembly_api_key_encrypted = :encrypted_key,
                    "updatedAt" = NOW()
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id, "encrypted_key": encrypted_key},
        )
        if (result.rowcount or 0) == 0:
            raise ValueError(f"User {user_id} not found")
        await db.commit()

    @staticmethod
    async def set_user_youtube_cookies(
        db: AsyncSession,
        user_id: str,
        encrypted_value: str,
        filename: str,
    ) -> None:
        """Store encrypted YouTube cookies for a user."""
        result = await db.execute(
            text(
                """
                UPDATE users
                SET youtube_cookies_encrypted = :encrypted_value,
                    youtube_cookies_filename = :filename,
                    youtube_cookies_updated_at = NOW(),
                    "updatedAt" = NOW()
                WHERE id = :user_id
                """
            ),
            {
                "user_id": user_id,
                "encrypted_value": encrypted_value,
                "filename": filename,
            },
        )
        if (result.rowcount or 0) == 0:
            raise ValueError(f"User {user_id} not found")
        await db.commit()

    @staticmethod
    async def clear_user_encrypted_assembly_key(db: AsyncSession, user_id: str) -> None:
        """Clear stored encrypted AssemblyAI key for a user."""
        result = await db.execute(
            text(
                """
                UPDATE users
                SET assembly_api_key_encrypted = NULL,
                    "updatedAt" = NOW()
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id},
        )
        if (result.rowcount or 0) == 0:
            raise ValueError(f"User {user_id} not found")
        await db.commit()

    @staticmethod
    async def clear_user_youtube_cookies(db: AsyncSession, user_id: str) -> None:
        """Clear stored YouTube cookies for a user."""
        result = await db.execute(
            text(
                """
                UPDATE users
                SET youtube_cookies_encrypted = NULL,
                    youtube_cookies_filename = NULL,
                    youtube_cookies_updated_at = NULL,
                    "updatedAt" = NOW()
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id},
        )
        if (result.rowcount or 0) == 0:
            raise ValueError(f"User {user_id} not found")
        await db.commit()

    @staticmethod
    async def set_user_encrypted_ai_key(
        db: AsyncSession,
        user_id: str,
        provider: str,
        encrypted_key: str,
    ) -> None:
        """Store encrypted LLM provider API key for a user."""
        column = LLM_PROVIDER_COLUMNS.get(provider)
        if not column:
            raise ValueError(f"Unsupported AI provider: {provider}")
        result = await db.execute(
            text(
                f"""
                UPDATE users
                SET {column} = :encrypted_key,
                    "updatedAt" = NOW()
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id, "encrypted_key": encrypted_key},
        )
        if (result.rowcount or 0) == 0:
            raise ValueError(f"User {user_id} not found")
        await db.commit()

    @staticmethod
    async def clear_user_encrypted_ai_key(
        db: AsyncSession,
        user_id: str,
        provider: str,
    ) -> None:
        """Clear encrypted LLM provider API key for a user."""
        column = LLM_PROVIDER_COLUMNS.get(provider)
        if not column:
            raise ValueError(f"Unsupported AI provider: {provider}")
        result = await db.execute(
            text(
                f"""
                UPDATE users
                SET {column} = NULL,
                    "updatedAt" = NOW()
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id},
        )
        if (result.rowcount or 0) == 0:
            raise ValueError(f"User {user_id} not found")
        await db.commit()

    @staticmethod
    async def get_user_ai_key_profile_encrypted(
        db: AsyncSession,
        user_id: str,
        provider: str,
        profile_name: str,
    ) -> Optional[str]:
        normalized_provider = (provider or "").strip().lower()
        normalized_profile = (profile_name or "").strip().lower()
        if normalized_provider not in LLM_PROVIDER_COLUMNS:
            raise ValueError(f"Unsupported AI provider: {provider}")
        if normalized_profile not in SUPPORTED_ZAI_KEY_PROFILES:
            raise ValueError(f"Unsupported key profile: {profile_name}")
        result = await db.execute(
            text(
                """
                SELECT api_key_encrypted
                FROM user_ai_key_profiles
                WHERE user_id = :user_id
                  AND provider = :provider
                  AND profile_name = :profile_name
                  AND enabled = true
                """
            ),
            {
                "user_id": user_id,
                "provider": normalized_provider,
                "profile_name": normalized_profile,
            },
        )
        row = result.fetchone()
        if not row:
            return None
        return row.api_key_encrypted

    @staticmethod
    async def list_user_ai_key_profiles(
        db: AsyncSession,
        user_id: str,
        provider: str,
    ) -> Dict[str, bool]:
        normalized_provider = (provider or "").strip().lower()
        if normalized_provider not in LLM_PROVIDER_COLUMNS:
            raise ValueError(f"Unsupported AI provider: {provider}")
        result = await db.execute(
            text(
                """
                SELECT profile_name, api_key_encrypted
                FROM user_ai_key_profiles
                WHERE user_id = :user_id
                  AND provider = :provider
                  AND enabled = true
                """
            ),
            {
                "user_id": user_id,
                "provider": normalized_provider,
            },
        )
        presence = {name: False for name in SUPPORTED_ZAI_KEY_PROFILES}
        for row in result.fetchall():
            profile_name = (getattr(row, "profile_name", "") or "").strip().lower()
            if profile_name in presence:
                presence[profile_name] = bool(getattr(row, "api_key_encrypted", None))
        return presence

    @staticmethod
    async def set_user_ai_key_profile(
        db: AsyncSession,
        user_id: str,
        provider: str,
        profile_name: str,
        encrypted_key: str,
    ) -> None:
        normalized_provider = (provider or "").strip().lower()
        normalized_profile = (profile_name or "").strip().lower()
        if normalized_provider not in LLM_PROVIDER_COLUMNS:
            raise ValueError(f"Unsupported AI provider: {provider}")
        if normalized_profile not in SUPPORTED_ZAI_KEY_PROFILES:
            raise ValueError(f"Unsupported key profile: {profile_name}")
        result = await db.execute(
            text(
                """
                INSERT INTO user_ai_key_profiles (
                    id,
                    user_id,
                    provider,
                    profile_name,
                    api_key_encrypted,
                    enabled,
                    created_at,
                    updated_at
                )
                VALUES (
                    :id,
                    :user_id,
                    :provider,
                    :profile_name,
                    :encrypted_key,
                    true,
                    NOW(),
                    NOW()
                )
                ON CONFLICT (user_id, provider, profile_name)
                DO UPDATE SET
                    api_key_encrypted = EXCLUDED.api_key_encrypted,
                    enabled = true,
                    updated_at = NOW()
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "provider": normalized_provider,
                "profile_name": normalized_profile,
                "encrypted_key": encrypted_key,
            },
        )
        if (result.rowcount or 0) == 0:
            raise ValueError("Failed to save key profile")
        await db.commit()

    @staticmethod
    async def clear_user_ai_key_profile(
        db: AsyncSession,
        user_id: str,
        provider: str,
        profile_name: str,
    ) -> None:
        normalized_provider = (provider or "").strip().lower()
        normalized_profile = (profile_name or "").strip().lower()
        if normalized_provider not in LLM_PROVIDER_COLUMNS:
            raise ValueError(f"Unsupported AI provider: {provider}")
        if normalized_profile not in SUPPORTED_ZAI_KEY_PROFILES:
            raise ValueError(f"Unsupported key profile: {profile_name}")
        await db.execute(
            text(
                """
                DELETE FROM user_ai_key_profiles
                WHERE user_id = :user_id
                  AND provider = :provider
                  AND profile_name = :profile_name
                """
            ),
            {
                "user_id": user_id,
                "provider": normalized_provider,
                "profile_name": normalized_profile,
            },
        )
        await db.commit()

    @staticmethod
    async def get_user_zai_routing_mode(db: AsyncSession, user_id: str) -> str:
        result = await db.execute(
            text(
                """
                SELECT default_zai_key_routing_mode
                FROM users
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id},
        )
        row = result.fetchone()
        if not row:
            raise ValueError(f"User {user_id} not found")
        mode = (getattr(row, "default_zai_key_routing_mode", "auto") or "auto").strip().lower()
        if mode not in SUPPORTED_ZAI_ROUTING_MODES:
            return "auto"
        return mode

    @staticmethod
    async def set_user_zai_routing_mode(db: AsyncSession, user_id: str, routing_mode: str) -> str:
        normalized_mode = (routing_mode or "").strip().lower()
        if normalized_mode not in SUPPORTED_ZAI_ROUTING_MODES:
            raise ValueError(f"Unsupported zai routing mode: {routing_mode}")
        result = await db.execute(
            text(
                """
                UPDATE users
                SET default_zai_key_routing_mode = :routing_mode,
                    "updatedAt" = NOW()
                WHERE id = :user_id
                """
            ),
            {
                "user_id": user_id,
                "routing_mode": normalized_mode,
            },
        )
        if (result.rowcount or 0) == 0:
            raise ValueError(f"User {user_id} not found")
        await db.commit()
        return normalized_mode

    @staticmethod
    async def get_user_default_ollama_profile(db: AsyncSession, user_id: str) -> Optional[str]:
        result = await db.execute(
            text(
                """
                SELECT default_ollama_profile
                FROM users
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id},
        )
        row = result.fetchone()
        if not row:
            raise ValueError(f"User {user_id} not found")
        value = (getattr(row, "default_ollama_profile", None) or "").strip()
        return value or None

    @staticmethod
    async def list_user_ollama_profiles(db: AsyncSession, user_id: str) -> List[Dict[str, Any]]:
        result = await db.execute(
            text(
                """
                SELECT
                    profile_name,
                    base_url,
                    auth_mode,
                    auth_header_name,
                    enabled,
                    is_default,
                    created_at,
                    updated_at,
                    CASE
                        WHEN auth_secret_encrypted IS NULL THEN false
                        ELSE length(trim(auth_secret_encrypted)) > 0
                    END AS has_auth_secret
                FROM user_ollama_server_profiles
                WHERE user_id = :user_id
                ORDER BY is_default DESC, profile_name ASC
                """
            ),
            {"user_id": user_id},
        )
        rows = result.fetchall()
        profiles: List[Dict[str, Any]] = []
        for row in rows:
            profiles.append(
                {
                    "profile_name": row.profile_name,
                    "base_url": row.base_url,
                    "auth_mode": row.auth_mode,
                    "auth_header_name": getattr(row, "auth_header_name", None),
                    "enabled": bool(getattr(row, "enabled", True)),
                    "is_default": bool(getattr(row, "is_default", False)),
                    "has_auth_secret": bool(getattr(row, "has_auth_secret", False)),
                    "created_at": getattr(row, "created_at", None),
                    "updated_at": getattr(row, "updated_at", None),
                }
            )
        return profiles

    @staticmethod
    async def get_user_ollama_profile(
        db: AsyncSession,
        user_id: str,
        profile_name: str,
        *,
        include_secret: bool = False,
    ) -> Optional[Dict[str, Any]]:
        normalized_profile = (profile_name or "").strip()
        if not normalized_profile:
            raise ValueError("profile_name is required")
        columns = """
            profile_name,
            base_url,
            auth_mode,
            auth_header_name,
            enabled,
            is_default,
            created_at,
            updated_at,
            CASE
                WHEN auth_secret_encrypted IS NULL THEN false
                ELSE length(trim(auth_secret_encrypted)) > 0
            END AS has_auth_secret
        """
        if include_secret:
            columns = f"{columns}, auth_secret_encrypted"
        result = await db.execute(
            text(
                f"""
                SELECT {columns}
                FROM user_ollama_server_profiles
                WHERE user_id = :user_id
                  AND profile_name = :profile_name
                """
            ),
            {
                "user_id": user_id,
                "profile_name": normalized_profile,
            },
        )
        row = result.fetchone()
        if not row:
            return None
        profile: Dict[str, Any] = {
            "profile_name": row.profile_name,
            "base_url": row.base_url,
            "auth_mode": row.auth_mode,
            "auth_header_name": getattr(row, "auth_header_name", None),
            "enabled": bool(getattr(row, "enabled", True)),
            "is_default": bool(getattr(row, "is_default", False)),
            "has_auth_secret": bool(getattr(row, "has_auth_secret", False)),
            "created_at": getattr(row, "created_at", None),
            "updated_at": getattr(row, "updated_at", None),
        }
        if include_secret:
            profile["auth_secret_encrypted"] = getattr(row, "auth_secret_encrypted", None)
        return profile

    @staticmethod
    async def set_user_ollama_profile(
        db: AsyncSession,
        user_id: str,
        profile_name: str,
        base_url: str,
        auth_mode: str,
        auth_header_name: Optional[str],
        auth_secret_encrypted: Optional[str],
        *,
        replace_auth_secret: bool = False,
        enabled: bool = True,
        set_as_default: bool = False,
    ) -> Dict[str, Any]:
        normalized_profile = (profile_name or "").strip()
        normalized_base_url = (base_url or "").strip()
        normalized_auth_mode = (auth_mode or "none").strip().lower()
        normalized_header_name = (auth_header_name or "").strip() or None
        if not normalized_profile:
            raise ValueError("profile_name is required")
        if not normalized_base_url:
            raise ValueError("base_url is required")
        if normalized_auth_mode not in SUPPORTED_OLLAMA_AUTH_MODES:
            raise ValueError(f"Unsupported Ollama auth mode: {auth_mode}")

        await db.execute(
            text(
                """
                INSERT INTO user_ollama_server_profiles (
                    id,
                    user_id,
                    profile_name,
                    base_url,
                    auth_mode,
                    auth_header_name,
                    auth_secret_encrypted,
                    enabled,
                    is_default,
                    created_at,
                    updated_at
                )
                VALUES (
                    :id,
                    :user_id,
                    :profile_name,
                    :base_url,
                    :auth_mode,
                    :auth_header_name,
                    :auth_secret_encrypted,
                    :enabled,
                    false,
                    NOW(),
                    NOW()
                )
                ON CONFLICT (user_id, profile_name)
                DO UPDATE SET
                    base_url = EXCLUDED.base_url,
                    auth_mode = EXCLUDED.auth_mode,
                    auth_header_name = EXCLUDED.auth_header_name,
                    auth_secret_encrypted = CASE
                        WHEN :replace_auth_secret THEN :auth_secret_encrypted
                        ELSE user_ollama_server_profiles.auth_secret_encrypted
                    END,
                    enabled = EXCLUDED.enabled,
                    updated_at = NOW()
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "profile_name": normalized_profile,
                "base_url": normalized_base_url,
                "auth_mode": normalized_auth_mode,
                "auth_header_name": normalized_header_name,
                "auth_secret_encrypted": auth_secret_encrypted,
                "replace_auth_secret": bool(replace_auth_secret),
                "enabled": bool(enabled),
            },
        )

        should_set_default = bool(set_as_default and enabled)
        if not should_set_default:
            default_presence = await db.execute(
                text(
                    """
                    SELECT 1
                    FROM user_ollama_server_profiles
                    WHERE user_id = :user_id
                      AND is_default = true
                      AND enabled = true
                    LIMIT 1
                    """
                ),
                {"user_id": user_id},
            )
            if default_presence.fetchone() is None and enabled:
                should_set_default = True

        if should_set_default:
            await db.execute(
                text(
                    """
                    UPDATE user_ollama_server_profiles
                    SET is_default = false,
                        updated_at = NOW()
                    WHERE user_id = :user_id
                    """
                ),
                {"user_id": user_id},
            )
            await db.execute(
                text(
                    """
                    UPDATE user_ollama_server_profiles
                    SET is_default = true,
                        updated_at = NOW()
                    WHERE user_id = :user_id
                      AND profile_name = :profile_name
                    """
                ),
                {
                    "user_id": user_id,
                    "profile_name": normalized_profile,
                },
            )
            user_update = await db.execute(
                text(
                    """
                    UPDATE users
                    SET default_ollama_profile = :profile_name,
                        default_ollama_base_url = :base_url,
                        "updatedAt" = NOW()
                    WHERE id = :user_id
                    """
                ),
                {
                    "user_id": user_id,
                    "profile_name": normalized_profile,
                    "base_url": normalized_base_url,
                },
            )
            if (user_update.rowcount or 0) == 0:
                raise ValueError(f"User {user_id} not found")
        else:
            await db.execute(
                text(
                    """
                    UPDATE users
                    SET default_ollama_base_url = :base_url,
                        "updatedAt" = NOW()
                    WHERE id = :user_id
                      AND default_ollama_profile = :profile_name
                    """
                ),
                {
                    "user_id": user_id,
                    "profile_name": normalized_profile,
                    "base_url": normalized_base_url,
                },
            )

        await db.commit()
        profile = await TaskRepository.get_user_ollama_profile(
            db,
            user_id,
            normalized_profile,
            include_secret=False,
        )
        if not profile:
            raise ValueError(f"Ollama profile {normalized_profile} not found after save")
        return profile

    @staticmethod
    async def delete_user_ollama_profile(
        db: AsyncSession,
        user_id: str,
        profile_name: str,
    ) -> bool:
        normalized_profile = (profile_name or "").strip()
        if not normalized_profile:
            raise ValueError("profile_name is required")

        deleted = await db.execute(
            text(
                """
                DELETE FROM user_ollama_server_profiles
                WHERE user_id = :user_id
                  AND profile_name = :profile_name
                RETURNING is_default
                """
            ),
            {
                "user_id": user_id,
                "profile_name": normalized_profile,
            },
        )
        deleted_row = deleted.fetchone()
        if not deleted_row:
            await db.rollback()
            return False

        deleted_was_default = bool(getattr(deleted_row, "is_default", False))
        if deleted_was_default:
            replacement = await db.execute(
                text(
                    """
                    SELECT profile_name, base_url
                    FROM user_ollama_server_profiles
                    WHERE user_id = :user_id
                      AND enabled = true
                    ORDER BY updated_at DESC, profile_name ASC
                    LIMIT 1
                    """
                ),
                {"user_id": user_id},
            )
            replacement_row = replacement.fetchone()
            if replacement_row:
                await db.execute(
                    text(
                        """
                        UPDATE user_ollama_server_profiles
                        SET is_default = false,
                            updated_at = NOW()
                        WHERE user_id = :user_id
                        """
                    ),
                    {"user_id": user_id},
                )
                await db.execute(
                    text(
                        """
                        UPDATE user_ollama_server_profiles
                        SET is_default = true,
                            updated_at = NOW()
                        WHERE user_id = :user_id
                          AND profile_name = :profile_name
                        """
                    ),
                    {
                        "user_id": user_id,
                        "profile_name": replacement_row.profile_name,
                    },
                )
                user_update = await db.execute(
                    text(
                        """
                        UPDATE users
                        SET default_ollama_profile = :profile_name,
                            default_ollama_base_url = :base_url,
                            "updatedAt" = NOW()
                        WHERE id = :user_id
                        """
                    ),
                    {
                        "user_id": user_id,
                        "profile_name": replacement_row.profile_name,
                        "base_url": replacement_row.base_url,
                    },
                )
                if (user_update.rowcount or 0) == 0:
                    raise ValueError(f"User {user_id} not found")
            else:
                user_update = await db.execute(
                    text(
                        """
                        UPDATE users
                        SET default_ollama_profile = NULL,
                            default_ollama_base_url = NULL,
                            "updatedAt" = NOW()
                        WHERE id = :user_id
                        """
                    ),
                    {"user_id": user_id},
                )
                if (user_update.rowcount or 0) == 0:
                    raise ValueError(f"User {user_id} not found")

        await db.commit()
        return True

    @staticmethod
    async def set_user_default_ollama_profile(
        db: AsyncSession,
        user_id: str,
        profile_name: str,
    ) -> str:
        normalized_profile = (profile_name or "").strip()
        if not normalized_profile:
            raise ValueError("profile_name is required")
        selected = await db.execute(
            text(
                """
                SELECT profile_name, base_url
                FROM user_ollama_server_profiles
                WHERE user_id = :user_id
                  AND profile_name = :profile_name
                  AND enabled = true
                LIMIT 1
                """
            ),
            {
                "user_id": user_id,
                "profile_name": normalized_profile,
            },
        )
        selected_row = selected.fetchone()
        if not selected_row:
            raise ValueError(f"Ollama profile not found or disabled: {normalized_profile}")

        await db.execute(
            text(
                """
                UPDATE user_ollama_server_profiles
                SET is_default = false,
                    updated_at = NOW()
                WHERE user_id = :user_id
                """
            ),
            {"user_id": user_id},
        )
        await db.execute(
            text(
                """
                UPDATE user_ollama_server_profiles
                SET is_default = true,
                    updated_at = NOW()
                WHERE user_id = :user_id
                  AND profile_name = :profile_name
                """
            ),
            {
                "user_id": user_id,
                "profile_name": normalized_profile,
            },
        )
        user_update = await db.execute(
            text(
                """
                UPDATE users
                SET default_ollama_profile = :profile_name,
                    default_ollama_base_url = :base_url,
                    "updatedAt" = NOW()
                WHERE id = :user_id
                """
            ),
            {
                "user_id": user_id,
                "profile_name": normalized_profile,
                "base_url": selected_row.base_url,
            },
        )
        if (user_update.rowcount or 0) == 0:
            raise ValueError(f"User {user_id} not found")
        await db.commit()
        return normalized_profile

    @staticmethod
    async def get_user_ollama_request_controls(db: AsyncSession, user_id: str) -> Dict[str, Optional[int]]:
        result = await db.execute(
            text(
                """
                SELECT
                    default_ollama_timeout_seconds,
                    default_ollama_max_retries,
                    default_ollama_retry_backoff_ms
                FROM users
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id},
        )
        row = result.fetchone()
        if not row:
            raise ValueError(f"User {user_id} not found")
        return {
            "timeout_seconds": getattr(row, "default_ollama_timeout_seconds", None),
            "max_retries": getattr(row, "default_ollama_max_retries", None),
            "retry_backoff_ms": getattr(row, "default_ollama_retry_backoff_ms", None),
        }

    @staticmethod
    async def set_user_ollama_request_controls(
        db: AsyncSession,
        user_id: str,
        *,
        timeout_seconds: Optional[int] = None,
        max_retries: Optional[int] = None,
        retry_backoff_ms: Optional[int] = None,
    ) -> Dict[str, Optional[int]]:
        set_clauses: List[str] = []
        params: Dict[str, Any] = {"user_id": user_id}
        if timeout_seconds is not None:
            set_clauses.append("default_ollama_timeout_seconds = :timeout_seconds")
            params["timeout_seconds"] = int(timeout_seconds)
        if max_retries is not None:
            set_clauses.append("default_ollama_max_retries = :max_retries")
            params["max_retries"] = int(max_retries)
        if retry_backoff_ms is not None:
            set_clauses.append("default_ollama_retry_backoff_ms = :retry_backoff_ms")
            params["retry_backoff_ms"] = int(retry_backoff_ms)

        if not set_clauses:
            raise ValueError("At least one Ollama request control must be provided")

        set_clauses.append('"updatedAt" = NOW()')
        query = f"UPDATE users SET {', '.join(set_clauses)} WHERE id = :user_id"
        result = await db.execute(text(query), params)
        if (result.rowcount or 0) == 0:
            raise ValueError(f"User {user_id} not found")
        await db.commit()
        return await TaskRepository.get_user_ollama_request_controls(db, user_id)

    @staticmethod
    async def get_user_ollama_base_url(db: AsyncSession, user_id: str) -> Optional[str]:
        result = await db.execute(
            text(
                """
                SELECT default_ollama_base_url
                FROM users
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id},
        )
        row = result.fetchone()
        if not row:
            raise ValueError(f"User {user_id} not found")
        value = (getattr(row, "default_ollama_base_url", None) or "").strip()
        return value or None

    @staticmethod
    async def set_user_ollama_base_url(db: AsyncSession, user_id: str, base_url: str) -> str:
        normalized_base_url = (base_url or "").strip()
        if not normalized_base_url:
            raise ValueError("Ollama server URL is required")
        result = await db.execute(
            text(
                """
                UPDATE users
                SET default_ollama_base_url = :base_url,
                    "updatedAt" = NOW()
                WHERE id = :user_id
                """
            ),
            {
                "user_id": user_id,
                "base_url": normalized_base_url,
            },
        )
        if (result.rowcount or 0) == 0:
            raise ValueError(f"User {user_id} not found")
        await db.commit()
        return normalized_base_url

    @staticmethod
    async def clear_user_ollama_base_url(db: AsyncSession, user_id: str) -> None:
        result = await db.execute(
            text(
                """
                UPDATE users
                SET default_ollama_base_url = NULL,
                    "updatedAt" = NOW()
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id},
        )
        if (result.rowcount or 0) == 0:
            raise ValueError(f"User {user_id} not found")
        await db.commit()

    @staticmethod
    async def user_exists(db: AsyncSession, user_id: str) -> bool:
        """Check if a user exists in the database."""
        result = await db.execute(
            text("SELECT 1 FROM users WHERE id = :user_id"),
            {"user_id": user_id}
        )
        return result.fetchone() is not None

    @staticmethod
    async def get_user_default_timeline_editor_enabled(db: AsyncSession, user_id: str) -> bool:
        """Get user-level default toggle for interactive timeline editor."""
        result = await db.execute(
            text("SELECT default_timeline_editor_enabled FROM users WHERE id = :user_id"),
            {"user_id": user_id},
        )
        row = result.fetchone()
        if not row:
            return True
        return bool(getattr(row, "default_timeline_editor_enabled", True))

    @staticmethod
    async def get_user_default_review_before_render_enabled(db: AsyncSession, user_id: str) -> bool:
        """Get user-level default toggle for review-before-render workflow."""
        result = await db.execute(
            text("SELECT default_review_before_render_enabled FROM users WHERE id = :user_id"),
            {"user_id": user_id},
        )
        row = result.fetchone()
        if not row:
            return True
        return bool(getattr(row, "default_review_before_render_enabled", True))

    @staticmethod
    async def get_user_default_video_preferences(db: AsyncSession, user_id: str) -> Dict[str, Any]:
        """Get user-level framing defaults used for new tasks and draft review."""
        result = await db.execute(
            text(
                """
                SELECT
                    default_review_before_render_enabled,
                    default_timeline_editor_enabled,
                    default_processing_profile,
                    default_framing_mode,
                    default_face_detection_mode,
                    default_fallback_crop_position,
                    default_face_anchor_profile
                FROM users
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id},
        )
        row = result.fetchone()
        if not row:
            return {
                "review_before_render_enabled": True,
                "timeline_editor_enabled": True,
                "default_processing_profile": "balanced",
                "default_framing_mode": "auto",
                "default_face_detection_mode": "balanced",
                "default_fallback_crop_position": "center",
                "default_face_anchor_profile": "auto",
            }
        return {
            "review_before_render_enabled": bool(getattr(row, "default_review_before_render_enabled", True)),
            "timeline_editor_enabled": bool(getattr(row, "default_timeline_editor_enabled", True)),
            "default_processing_profile": str(
                getattr(row, "default_processing_profile", "balanced") or "balanced"
            ),
            "default_framing_mode": str(getattr(row, "default_framing_mode", "auto") or "auto"),
            "default_face_detection_mode": str(
                getattr(row, "default_face_detection_mode", "balanced") or "balanced"
            ),
            "default_fallback_crop_position": str(
                getattr(row, "default_fallback_crop_position", "center") or "center"
            ),
            "default_face_anchor_profile": str(
                getattr(row, "default_face_anchor_profile", "auto") or "auto"
            ),
        }

    @staticmethod
    async def get_failure_summary(db: AsyncSession, limit: int = 5) -> List[Dict[str, Any]]:
        result = await db.execute(
            text(
                """
                SELECT
                    COALESCE(NULLIF(TRIM(failure_code), ''), 'system') AS failure_code,
                    COUNT(*) AS failure_count,
                    MAX(updated_at) AS last_failure_at,
                    MIN(progress_message) FILTER (WHERE progress_message IS NOT NULL) AS representative_message
                FROM tasks
                WHERE status = 'error'
                GROUP BY COALESCE(NULLIF(TRIM(failure_code), ''), 'system')
                ORDER BY MAX(updated_at) DESC, COUNT(*) DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
        return [
            {
                "failure_code": str(row.failure_code or "system"),
                "count": int(row.failure_count or 0),
                "last_failure_at": row.last_failure_at,
                "representative_message": getattr(row, "representative_message", None),
            }
            for row in result.fetchall()
        ]

    @staticmethod
    async def get_recent_failed_tasks(db: AsyncSession, limit: int = 10) -> List[Dict[str, Any]]:
        result = await db.execute(
            text(
                """
                SELECT
                    t.id,
                    t.failure_code,
                    t.failure_hint,
                    t.progress_message,
                    t.updated_at,
                    s.title AS source_title
                FROM tasks t
                LEFT JOIN sources s ON s.id = t.source_id
                WHERE t.status = 'error'
                ORDER BY t.updated_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
        return [
            {
                "id": row.id,
                "source_title": getattr(row, "source_title", None),
                "failure_code": getattr(row, "failure_code", None) or "system",
                "failure_hint": getattr(row, "failure_hint", None),
                "message": getattr(row, "progress_message", None),
                "updated_at": row.updated_at,
            }
            for row in result.fetchall()
        ]

    @staticmethod
    async def update_task_timeline_editor_enabled(db: AsyncSession, task_id: str, enabled: bool) -> None:
        """Update per-task timeline editor toggle."""
        await db.execute(
            text(
                """
                UPDATE tasks
                SET timeline_editor_enabled = :enabled,
                    updated_at = NOW()
                WHERE id = :task_id
                """
            ),
            {"task_id": task_id, "enabled": bool(enabled)},
        )
        await db.commit()

    @staticmethod
    async def delete_task(db: AsyncSession, task_id: str) -> None:
        """Delete a task by ID."""
        await db.execute(
            text("DELETE FROM tasks WHERE id = :task_id"),
            {"task_id": task_id}
        )
        await db.commit()
        logger.info(f"Deleted task {task_id}")

    @staticmethod
    async def delete_tasks_by_user(db: AsyncSession, user_id: str) -> int:
        """Delete all tasks for a user. Returns count of deleted tasks."""
        result = await db.execute(
            text("DELETE FROM tasks WHERE user_id = :user_id"),
            {"user_id": user_id},
        )
        await db.commit()
        deleted_count = result.rowcount or 0
        logger.info(f"Deleted {deleted_count} tasks for user {user_id}")
        return deleted_count

    @staticmethod
    async def cancel_active_tasks(
        db: AsyncSession,
        progress_message: str = "Cancelled by admin action"
    ) -> List[str]:
        """
        Mark all active tasks as error and return affected task IDs.
        Active = queued or processing.
        """
        result = await db.execute(
            text(
                """
                UPDATE tasks
                SET status = 'error',
                    progress_message = :progress_message,
                    updated_at = NOW()
                WHERE status IN ('queued', 'processing')
                RETURNING id
                """
            ),
            {"progress_message": progress_message},
        )
        await db.commit()
        task_ids = [row.id for row in result.fetchall()]
        logger.info(f"Cancelled {len(task_ids)} active tasks")
        return task_ids
