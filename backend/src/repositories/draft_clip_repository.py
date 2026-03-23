"""
Draft clip repository - handles all database operations for task_clip_drafts.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession


class DraftClipRepository:
    """Repository for editable task draft clips."""

    @staticmethod
    async def replace_task_drafts(
        db: AsyncSession,
        task_id: str,
        drafts: List[Dict[str, Any]],
    ) -> List[str]:
        """Delete existing drafts for a task and insert a new ordered set."""
        await db.execute(
            sql_text("DELETE FROM task_clip_drafts WHERE task_id = :task_id"),
            {"task_id": task_id},
        )

        created_ids: List[str] = []
        for draft in drafts:
            result = await db.execute(
                sql_text(
                    """
                    INSERT INTO task_clip_drafts (
                        id,
                        task_id,
                        clip_order,
                        start_time,
                        end_time,
                        duration,
                        original_start_time,
                        original_end_time,
                        original_duration,
                        original_text,
                        edited_text,
                        relevance_score,
                        review_score,
                        feedback_score_adjustment,
                        feedback_signals_json,
                        reasoning,
                        created_by_user,
                        is_selected,
                        is_deleted,
                        edited_word_timings_json,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        :id,
                        :task_id,
                        :clip_order,
                        :start_time,
                        :end_time,
                        :duration,
                        :original_start_time,
                        :original_end_time,
                        :original_duration,
                        :original_text,
                        :edited_text,
                        :relevance_score,
                        :review_score,
                        :feedback_score_adjustment,
                        :feedback_signals_json,
                        :reasoning,
                        :created_by_user,
                        :is_selected,
                        :is_deleted,
                        :edited_word_timings_json,
                        NOW(),
                        NOW()
                    )
                    RETURNING id
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "task_id": task_id,
                    "clip_order": int(draft["clip_order"]),
                    "start_time": str(draft["start_time"]),
                    "end_time": str(draft["end_time"]),
                    "duration": float(draft["duration"]),
                    "original_start_time": str(draft.get("original_start_time") or draft["start_time"]),
                    "original_end_time": str(draft.get("original_end_time") or draft["end_time"]),
                    "original_duration": float(draft.get("original_duration") or draft["duration"]),
                    "original_text": draft.get("original_text"),
                    "edited_text": draft.get("edited_text"),
                    "relevance_score": float(draft["relevance_score"]),
                    "review_score": float(
                        draft.get("review_score")
                        if draft.get("review_score") is not None
                        else draft["relevance_score"]
                    ),
                    "feedback_score_adjustment": float(draft.get("feedback_score_adjustment") or 0.0),
                    "feedback_signals_json": draft.get("feedback_signals_json") or {},
                    "reasoning": draft.get("reasoning"),
                    "created_by_user": bool(draft.get("created_by_user", False)),
                    "is_selected": bool(draft.get("is_selected", True)),
                    "is_deleted": bool(draft.get("is_deleted", False)),
                    "edited_word_timings_json": draft.get("edited_word_timings_json"),
                },
            )
            created_ids.append(str(result.scalar()))

        await db.commit()
        return created_ids

    @staticmethod
    async def get_drafts_by_task(
        db: AsyncSession,
        task_id: str,
        include_deleted: bool = False,
    ) -> List[Dict[str, Any]]:
        where_deleted = "" if include_deleted else "AND is_deleted = false"
        result = await db.execute(
            sql_text(
                """
                SELECT
                    id,
                    task_id,
                    clip_order,
                    start_time,
                    end_time,
                    duration,
                    original_start_time,
                    original_end_time,
                    original_duration,
                    original_text,
                    edited_text,
                    relevance_score,
                    review_score,
                    feedback_score_adjustment,
                    feedback_signals_json,
                    reasoning,
                    created_by_user,
                    is_selected,
                    is_deleted,
                    edited_word_timings_json,
                    created_at,
                    updated_at
                FROM task_clip_drafts
                WHERE task_id = :task_id
                """ + where_deleted + """
                ORDER BY clip_order ASC
                """
            ),
            {"task_id": task_id},
        )

        drafts: List[Dict[str, Any]] = []
        for row in result.fetchall():
            drafts.append(
                {
                    "id": row.id,
                    "task_id": row.task_id,
                    "clip_order": row.clip_order,
                    "start_time": row.start_time,
                    "end_time": row.end_time,
                    "duration": float(row.duration),
                    "original_start_time": row.original_start_time,
                    "original_end_time": row.original_end_time,
                    "original_duration": float(row.original_duration),
                    "original_text": row.original_text,
                    "edited_text": row.edited_text,
                    "relevance_score": float(row.relevance_score),
                    "review_score": float(row.review_score),
                    "feedback_score_adjustment": float(row.feedback_score_adjustment),
                    "feedback_signals_json": row.feedback_signals_json or {},
                    "reasoning": row.reasoning,
                    "created_by_user": bool(row.created_by_user),
                    "is_selected": bool(row.is_selected),
                    "is_deleted": bool(row.is_deleted),
                    "edited_word_timings_json": row.edited_word_timings_json,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                }
            )

        return drafts

    @staticmethod
    async def get_draft_map_by_task(
        db: AsyncSession,
        task_id: str,
        include_deleted: bool = False,
    ) -> Dict[str, Dict[str, Any]]:
        drafts = await DraftClipRepository.get_drafts_by_task(db, task_id, include_deleted=include_deleted)
        return {draft["id"]: draft for draft in drafts}

    @staticmethod
    async def bulk_update_drafts(
        db: AsyncSession,
        task_id: str,
        updates: List[Dict[str, Any]],
        *,
        include_deleted: bool = False,
    ) -> None:
        for update in updates:
            draft_id = str(update["id"])
            set_clauses = ["updated_at = NOW()"]
            params: Dict[str, Any] = {
                "task_id": task_id,
                "draft_id": draft_id,
            }

            if "clip_order" in update:
                set_clauses.append("clip_order = :clip_order")
                params["clip_order"] = int(update["clip_order"])
            if "start_time" in update:
                set_clauses.append("start_time = :start_time")
                params["start_time"] = str(update["start_time"])
            if "end_time" in update:
                set_clauses.append("end_time = :end_time")
                params["end_time"] = str(update["end_time"])
            if "duration" in update:
                set_clauses.append("duration = :duration")
                params["duration"] = float(update["duration"])
            if "edited_text" in update:
                set_clauses.append("edited_text = :edited_text")
                params["edited_text"] = update.get("edited_text")
            if "is_selected" in update:
                set_clauses.append("is_selected = :is_selected")
                params["is_selected"] = bool(update["is_selected"])
            if "is_deleted" in update:
                set_clauses.append("is_deleted = :is_deleted")
                params["is_deleted"] = bool(update["is_deleted"])
            if "edited_word_timings_json" in update:
                set_clauses.append("edited_word_timings_json = :edited_word_timings_json")
                params["edited_word_timings_json"] = update.get("edited_word_timings_json")
            if "review_score" in update:
                set_clauses.append("review_score = :review_score")
                params["review_score"] = float(update["review_score"])
            if "feedback_score_adjustment" in update:
                set_clauses.append("feedback_score_adjustment = :feedback_score_adjustment")
                params["feedback_score_adjustment"] = float(update["feedback_score_adjustment"])
            if "feedback_signals_json" in update:
                set_clauses.append("feedback_signals_json = :feedback_signals_json")
                params["feedback_signals_json"] = update.get("feedback_signals_json")

            await db.execute(
                sql_text(
                    f"""
                    UPDATE task_clip_drafts
                    SET {', '.join(set_clauses)}
                    WHERE task_id = :task_id AND id = :draft_id
                    {"AND is_deleted = false" if not include_deleted else ""}
                    """
                ),
                params,
            )

        await db.commit()

    @staticmethod
    async def count_selected_drafts(db: AsyncSession, task_id: str) -> int:
        result = await db.execute(
            sql_text(
                """
                SELECT COUNT(*) AS count
                FROM task_clip_drafts
                WHERE task_id = :task_id
                  AND is_selected = true
                  AND is_deleted = false
                """
            ),
            {"task_id": task_id},
        )
        return int(result.scalar() or 0)

    @staticmethod
    async def delete_drafts_by_task(db: AsyncSession, task_id: str) -> int:
        result = await db.execute(
            sql_text("DELETE FROM task_clip_drafts WHERE task_id = :task_id"),
            {"task_id": task_id},
        )
        await db.commit()
        return int(result.rowcount or 0)

    @staticmethod
    async def update_draft_word_timings(
        db: AsyncSession,
        task_id: str,
        draft_id: str,
        word_timings: Optional[List[Dict[str, Any]]],
    ) -> None:
        await db.execute(
            sql_text(
                """
                    UPDATE task_clip_drafts
                    SET edited_word_timings_json = :word_timings,
                        updated_at = NOW()
                    WHERE task_id = :task_id AND id = :draft_id AND is_deleted = false
                """
            ),
            {
                "task_id": task_id,
                "draft_id": draft_id,
                "word_timings": word_timings,
            },
        )
        await db.commit()

    @staticmethod
    async def get_next_clip_order(db: AsyncSession, task_id: str) -> int:
        result = await db.execute(
            sql_text(
                """
                SELECT COALESCE(MAX(clip_order), 0) AS max_order
                FROM task_clip_drafts
                WHERE task_id = :task_id
                """
            ),
            {"task_id": task_id},
        )
        max_order = int(result.scalar() or 0)
        return max_order + 1

    @staticmethod
    async def create_draft(
        db: AsyncSession,
        task_id: str,
        draft: Dict[str, Any],
    ) -> str:
        draft_id = str(uuid.uuid4())
        result = await db.execute(
            sql_text(
                """
                INSERT INTO task_clip_drafts (
                    id,
                    task_id,
                    clip_order,
                    start_time,
                    end_time,
                    duration,
                    original_start_time,
                    original_end_time,
                    original_duration,
                    original_text,
                    edited_text,
                    relevance_score,
                    review_score,
                    feedback_score_adjustment,
                    feedback_signals_json,
                    reasoning,
                    created_by_user,
                    is_selected,
                    is_deleted,
                    edited_word_timings_json,
                    created_at,
                    updated_at
                )
                VALUES (
                    :id,
                    :task_id,
                    :clip_order,
                    :start_time,
                    :end_time,
                    :duration,
                    :original_start_time,
                    :original_end_time,
                    :original_duration,
                    :original_text,
                    :edited_text,
                    :relevance_score,
                    :review_score,
                    :feedback_score_adjustment,
                    :feedback_signals_json,
                    :reasoning,
                    :created_by_user,
                    :is_selected,
                    :is_deleted,
                    :edited_word_timings_json,
                    NOW(),
                    NOW()
                )
                RETURNING id
                """
            ),
            {
                "id": draft_id,
                "task_id": task_id,
                "clip_order": int(draft["clip_order"]),
                "start_time": str(draft["start_time"]),
                "end_time": str(draft["end_time"]),
                "duration": float(draft["duration"]),
                "original_start_time": str(draft.get("original_start_time") or draft["start_time"]),
                "original_end_time": str(draft.get("original_end_time") or draft["end_time"]),
                "original_duration": float(draft.get("original_duration") or draft["duration"]),
                "original_text": draft.get("original_text"),
                "edited_text": draft.get("edited_text"),
                "relevance_score": float(draft.get("relevance_score") or 0.0),
                "review_score": float(
                    draft.get("review_score")
                    if draft.get("review_score") is not None
                    else draft.get("relevance_score") or 0.0
                ),
                "feedback_score_adjustment": float(draft.get("feedback_score_adjustment") or 0.0),
                "feedback_signals_json": draft.get("feedback_signals_json") or {},
                "reasoning": draft.get("reasoning"),
                "created_by_user": bool(draft.get("created_by_user", False)),
                "is_selected": bool(draft.get("is_selected", True)),
                "is_deleted": bool(draft.get("is_deleted", False)),
                "edited_word_timings_json": draft.get("edited_word_timings_json"),
            },
        )
        await db.commit()
        return str(result.scalar())

    @staticmethod
    async def soft_delete_draft(db: AsyncSession, task_id: str, draft_id: str) -> bool:
        result = await db.execute(
            sql_text(
                """
                UPDATE task_clip_drafts
                SET is_deleted = true,
                    is_selected = false,
                    updated_at = NOW()
                WHERE task_id = :task_id
                  AND id = :draft_id
                  AND is_deleted = false
                """
            ),
            {
                "task_id": task_id,
                "draft_id": draft_id,
            },
        )
        await db.commit()
        return bool(result.rowcount)

    @staticmethod
    async def restore_task_drafts(db: AsyncSession, task_id: str) -> None:
        await db.execute(
            sql_text(
                """
                UPDATE task_clip_drafts
                SET start_time = original_start_time,
                    end_time = original_end_time,
                    duration = original_duration,
                    edited_text = original_text,
                    edited_word_timings_json = NULL,
                    is_selected = CASE
                        WHEN created_by_user THEN false
                        ELSE true
                    END,
                    is_deleted = CASE
                        WHEN created_by_user THEN true
                        ELSE false
                    END,
                    updated_at = NOW()
                WHERE task_id = :task_id
                """
            ),
            {"task_id": task_id},
        )
        await db.commit()
