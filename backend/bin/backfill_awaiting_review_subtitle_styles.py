#!/usr/bin/env python3
"""One-time helper to backfill tasks.subtitle_style for existing tasks."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill missing/partial subtitle_style for tasks.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute updates without writing to the database.",
    )
    parser.add_argument(
        "--include-existing",
        action="store_true",
        help="Also process tasks that already have subtitle_style.",
    )
    parser.add_argument(
        "--all-statuses",
        action="store_true",
        help="Process all task statuses (default processes only awaiting_review).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of candidate tasks to scan.",
    )
    parser.add_argument(
        "--user-id",
        type=str,
        default=None,
        help="Optional user_id filter.",
    )
    parser.add_argument(
        "--task-id",
        action="append",
        dest="task_ids",
        default=[],
        help="Specific task ID to include (can be repeated).",
    )
    return parser.parse_args()


async def _run() -> int:
    args = _parse_args()

    from src.database import AsyncSessionLocal, init_db
    from src.repositories.task_repository import TaskRepository
    from src.subtitle_style import normalize_subtitle_style
    from src.task_subtitle_style import build_normalized_subtitle_style_for_task

    if args.limit is not None and args.limit <= 0:
        print("--limit must be positive", file=sys.stderr)
        return 2

    await init_db()

    task_ids = [task_id.strip() for task_id in args.task_ids if isinstance(task_id, str) and task_id.strip()]
    statuses = None if args.all_statuses else ["awaiting_review"]

    async with AsyncSessionLocal() as db:
        repo = TaskRepository()
        task_rows = await repo.get_tasks_for_subtitle_style_backfill(
            db,
            statuses=statuses,
            user_id=(args.user_id or "").strip() or None,
            task_ids=task_ids or None,
            include_existing=bool(args.include_existing),
            limit=args.limit,
        )

        updates: Dict[str, Dict[str, Any]] = {}
        unchanged_count = 0
        for task_row in task_rows:
            normalized_style = build_normalized_subtitle_style_for_task(task_row)
            existing_style = task_row.get("subtitle_style")
            if isinstance(existing_style, dict):
                if normalize_subtitle_style(existing_style) == normalized_style:
                    unchanged_count += 1
                    continue
            updates[str(task_row["id"])] = normalized_style

        if args.dry_run:
            updated_count = len(updates)
        else:
            updated_count = await repo.update_task_subtitle_styles_bulk(db, updates)

    summary = {
        "dry_run": bool(args.dry_run),
        "scanned_tasks": len(task_rows),
        "would_update_tasks": len(updates),
        "updated_tasks": updated_count,
        "unchanged_tasks": unchanged_count,
        "updated_task_ids_preview": list(updates.keys())[:25],
    }
    print(json.dumps(summary, indent=2))
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
