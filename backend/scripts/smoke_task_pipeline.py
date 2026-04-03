from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

import httpx


async def wait_for_status(
    client: httpx.AsyncClient,
    *,
    api_url: str,
    user_id: str,
    task_id: str,
    target_statuses: set[str],
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while True:
        response = await client.get(f"{api_url}/tasks/{task_id}", headers={"user_id": user_id})
        response.raise_for_status()
        payload = response.json()
        status = str(payload.get("status") or "")
        if status in target_statuses:
            return payload
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError(f"Timed out waiting for task {task_id} to reach {sorted(target_statuses)}")
        await asyncio.sleep(2)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Manual smoke test for create -> transcript -> draft -> finalize pipeline.")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    args = parser.parse_args()

    async with httpx.AsyncClient(timeout=60.0) as client:
        create_response = await client.post(
            f"{args.api_url}/tasks/",
            headers={
                "Content-Type": "application/json",
                "user_id": args.user_id,
            },
            json={
                "source": {"url": args.source_url, "title": None},
                "processing_profile": "balanced",
                "review_before_render_enabled": True,
                "timeline_editor_enabled": True,
                "font_options": {},
                "transcription_options": {"provider": "local"},
                "ai_options": {"provider": "openai"},
            },
        )
        create_response.raise_for_status()
        create_payload = create_response.json()
        task_id = str(create_payload["task_id"])
        print(json.dumps({"task_id": task_id, "phase": "created"}, indent=2))

        review_task = await wait_for_status(
            client,
            api_url=args.api_url,
            user_id=args.user_id,
            task_id=task_id,
            target_statuses={"awaiting_review", "completed", "error"},
            timeout_seconds=args.timeout_seconds,
        )
        print(json.dumps({"phase": "after_analysis", "status": review_task.get("status")}, indent=2))
        if review_task.get("status") == "error":
            raise RuntimeError(f"Task failed before review: {review_task.get('progress_message')}")
        if review_task.get("status") == "completed":
            print(json.dumps({"phase": "complete_without_review", "task_id": task_id}, indent=2))
            return

        finalize_response = await client.post(
            f"{args.api_url}/tasks/{task_id}/finalize",
            headers={"user_id": args.user_id},
        )
        finalize_response.raise_for_status()
        print(json.dumps({"phase": "finalize_queued", "task_id": task_id}, indent=2))

        completed_task = await wait_for_status(
            client,
            api_url=args.api_url,
            user_id=args.user_id,
            task_id=task_id,
            target_statuses={"completed", "error"},
            timeout_seconds=args.timeout_seconds,
        )
        print(json.dumps({"phase": "finished", "status": completed_task.get("status")}, indent=2))
        if completed_task.get("status") == "error":
            raise RuntimeError(f"Task failed after finalize: {completed_task.get('progress_message')}")


if __name__ == "__main__":
    asyncio.run(main())
