"""
Task service - orchestrates task creation and processing workflow.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, Optional, Callable, Awaitable, List, Tuple, AsyncIterator
import logging
import asyncio
import re
import time
import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from ..repositories.task_repository import TaskRepository
from ..repositories.source_repository import SourceRepository
from ..repositories.clip_repository import ClipRepository
from ..repositories.draft_clip_repository import DraftClipRepository
from .video_service import VideoService
from .secret_service import SecretService
from .ai_model_catalog_service import (
    list_models_for_provider,
    pull_ollama_model as run_ollama_model_pull,
    test_ollama_connection as run_ollama_connection_test,
)
from ..config import Config

logger = logging.getLogger(__name__)
config = Config()
SUPPORTED_AI_PROVIDERS = {"openai", "google", "anthropic", "zai", "ollama"}
AI_KEY_REQUIRED_PROVIDERS = {"openai", "google", "anthropic", "zai"}
OLLAMA_RECOMMENDED_MODEL = "gpt-oss:latest"
DEFAULT_AI_MODELS = {
    "openai": "gpt-5-mini",
    "google": "gemini-2.5-pro",
    "anthropic": "claude-4-sonnet",
    "zai": "glm-5",
    "ollama": OLLAMA_RECOMMENDED_MODEL,
}
SUPPORTED_ZAI_ROUTING_MODES = {"auto", "subscription", "metered"}
SUPPORTED_ZAI_KEY_PROFILES = {"subscription", "metered"}
SUPPORTED_OLLAMA_AUTH_MODES = {"none", "bearer", "custom_header"}
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_PROFILE_NAME = "default"
DEFAULT_OLLAMA_TIMEOUT_SECONDS = 15
DEFAULT_OLLAMA_MAX_RETRIES = 2
DEFAULT_OLLAMA_RETRY_BACKOFF_MS = 400
MIN_OLLAMA_TIMEOUT_SECONDS = 1
MAX_OLLAMA_TIMEOUT_SECONDS = 600
MIN_OLLAMA_MAX_RETRIES = 0
MAX_OLLAMA_MAX_RETRIES = 10
MIN_OLLAMA_RETRY_BACKOFF_MS = 0
MAX_OLLAMA_RETRY_BACKOFF_MS = 30000
DRAFT_MIN_DURATION_SECONDS = 3
DRAFT_MAX_DURATION_SECONDS = 180
TIMELINE_INCREMENT_SECONDS = 0.5
REVIEW_DESELECT_PENALTY = -0.35
REVIEW_DELETE_PENALTY = -0.4
REVIEW_MANUAL_CLIP_BONUS = 0.25
REVIEW_TEXT_EDIT_BONUS = 0.07
REVIEW_TIMING_EDIT_BASE_BONUS = 0.03
REVIEW_TIMING_EDIT_PER_SECOND = 0.01
REVIEW_TIMING_EDIT_MAX_BONUS = 0.12
MIN_REVIEW_AUTO_SELECT_MIN_SCORE = 0.0
MAX_REVIEW_AUTO_SELECT_MIN_SCORE = 1.0
SUPPORTED_FRAMING_MODE_OVERRIDES = {"auto", "prefer_face", "fixed_position"}
SUPPORTED_FACE_DETECTION_MODES = {"balanced", "more_faces"}
SUPPORTED_FALLBACK_CROP_POSITIONS = {"center", "left_center", "right_center"}
SUPPORTED_PROCESSING_PROFILES = {"fast_draft", "balanced", "best_quality", "stream_layout"}
SUPPORTED_FACE_ANCHOR_PROFILES = {
    "auto",
    "left_only",
    "left_or_center",
    "center_only",
    "right_or_center",
    "right_only",
}
RETRYABLE_STAGE_ORDER = ("downloaded", "transcribed", "analyzed", "review_approved")
FAILURE_HINTS = {
    "download": "Check the source URL or uploaded file and retry from download.",
    "transcription": "Adjust the transcription provider or model and retry from transcription.",
    "ai_analysis": "Check AI provider settings or model availability and retry from analysis.",
    "draft_validation": "Fix draft overlaps or review selections, then retry from the last valid stage.",
    "render": "Review selected clips and retry rendering from the approved draft stage.",
    "storage": "Check disk space or output permissions and retry.",
    "system": "Inspect worker logs and runtime diagnostics, then retry from the latest checkpoint.",
}
CORRUPT_AUDIO_FAILURE_MARKERS = (
    "aac decode failure",
    "source audio stream is corrupted",
    "partially unreadable",
    "ffmpeg audio extraction failed",
    "invalid data found when processing input",
    "error submitting packet to decoder",
    "decode_pce",
    "channel element",
    "reserved bit set",
    "prediction is not allowed in aac-lc",
    "invalid band type",
    "decoding error",
)
_TIMESTAMP_SECONDS_RE = re.compile(r"^\d+(?:\.\d+)?$")
YOUTUBE_COOKIE_MAX_BYTES = 1024 * 1024
YOUTUBE_COOKIE_DOMAIN_MARKERS = ("youtube.com", ".youtube.com", "google.com", ".google.com")
DEFAULT_OLLAMA_VIABILITY_ATTEMPTS = 2
MIN_OLLAMA_VIABILITY_ATTEMPTS = 1
MAX_OLLAMA_VIABILITY_ATTEMPTS = 3
OLLAMA_MODEL_REQUEST_PRESETS: Tuple[Tuple[str, Dict[str, Any]], ...] = (
    (
        "qwen3-vl",
        {
            "timeout_seconds": 90,
            "max_retries": 1,
            "retry_backoff_ms": 250,
            "temperature": 0.0,
            "think": False,
        },
    ),
    (
        "deepseek-r1",
        {
            "timeout_seconds": 90,
            "max_retries": 1,
            "retry_backoff_ms": 250,
            "temperature": 0.0,
            "think": False,
        },
    ),
    (
        "qwen3",
        {
            "timeout_seconds": 90,
            "max_retries": 1,
            "retry_backoff_ms": 250,
            "temperature": 0.0,
            "think": False,
        },
    ),
    (
        "ministral",
        {
            "timeout_seconds": 90,
            "max_retries": 1,
            "retry_backoff_ms": 250,
            "temperature": 0.0,
        },
    ),
    (
        "magistral",
        {
            "timeout_seconds": 90,
            "max_retries": 1,
            "retry_backoff_ms": 250,
            "temperature": 0.0,
        },
    ),
    (
        "gpt-oss",
        {
            "timeout_seconds": 60,
            "max_retries": 1,
            "retry_backoff_ms": 250,
            "temperature": 0.0,
            "think": "low",
        },
    ),
)


class DraftOverlapError(ValueError):
    """Raised when one or more draft clips overlap on the review timeline."""

    def __init__(self, conflicts: List[Dict[str, Any]]):
        self.conflicts = conflicts
        message = "Draft clips overlap."
        if conflicts:
            first = conflicts[0]
            message = (
                "Draft clips overlap: "
                f"{first.get('left_label', 'Clip A')} and {first.get('right_label', 'Clip B')}"
            )
        super().__init__(message)
DEFAULT_OLLAMA_VIABILITY_TRANSCRIPT = """[00:00 - 00:12] Most creators miss this simple framing rule that can double watch time.
[00:12 - 00:25] If your first sentence does not create curiosity, viewers leave before the value appears.
[00:25 - 00:41] Start with a concrete promise, then prove it quickly with one clear example.
[00:41 - 00:58] For example: change from \"Here are some tips\" to \"Use this 20-second hook to stop the scroll.\"
[00:58 - 01:15] The second principle is momentum: each line should naturally force the next line.
[01:15 - 01:34] Ask a question, answer half of it, then reveal the key insight after a short pause.
[01:34 - 01:52] Third: keep only one core idea per clip so the audience can repeat it to someone else.
[01:52 - 02:09] Add emotion with contrast: \"I spent months guessing, then fixed it in one day.\"
[02:09 - 02:27] Close with a practical step people can apply immediately after watching.
[02:27 - 02:44] If viewers can act on one instruction right away, shares and saves usually increase.
[02:44 - 03:00] Recap: hook with a promise, build momentum, and end with one actionable takeaway."""


class TaskService:
    """Service for task workflow orchestration."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.task_repo = TaskRepository()
        self.source_repo = SourceRepository()
        self.clip_repo = ClipRepository()
        self.draft_clip_repo = DraftClipRepository()
        self.video_service = VideoService()
        self.secret_service = SecretService()

    @staticmethod
    def _has_env_youtube_cookie_fallback() -> bool:
        configured = (config.ytdlp_cookies_file or "").strip()
        return bool(configured and Path(configured).is_file())

    @staticmethod
    def _sanitize_youtube_cookie_filename(filename: str) -> str:
        candidate = Path(filename or "").name.strip()
        if not candidate:
            raise ValueError("No cookies file provided")
        if Path(candidate).suffix.lower() != ".txt":
            raise ValueError("Only .txt cookies files are supported")
        sanitized_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(candidate).stem).strip("-_.")
        if not sanitized_stem:
            raise ValueError("Invalid cookies filename")
        return f"{sanitized_stem}.txt"

    @classmethod
    def validate_youtube_cookies_upload(cls, filename: str, payload: bytes) -> Tuple[str, str]:
        sanitized_filename = cls._sanitize_youtube_cookie_filename(filename)
        if not payload:
            raise ValueError("Uploaded cookies file is empty")
        if len(payload) > YOUTUBE_COOKIE_MAX_BYTES:
            raise ValueError("Cookies file too large (max 1MB)")

        decoded_text: Optional[str] = None
        for encoding in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                decoded_text = payload.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if decoded_text is None:
            raise ValueError("Cookies file must be a plain text Netscape export")

        normalized_text = decoded_text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized_text:
            raise ValueError("Uploaded cookies file is empty")

        cookie_rows = [
            line for line in normalized_text.split("\n")
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if not cookie_rows or not any(line.count("\t") >= 6 for line in cookie_rows):
            raise ValueError("Invalid Netscape cookies.txt format")

        lowered_rows = "\n".join(cookie_rows).lower()
        if not any(marker in lowered_rows for marker in YOUTUBE_COOKIE_DOMAIN_MARKERS):
            raise ValueError("Cookies file does not appear to contain YouTube or Google cookies")

        return sanitized_filename, normalized_text

    @asynccontextmanager
    async def _resolved_youtube_cookie_file(self, user_id: Optional[str]) -> AsyncIterator[Optional[str]]:
        temp_path: Optional[Path] = None
        try:
            if user_id:
                stored_record = await self.task_repo.get_user_youtube_cookies(self.db, user_id)
                encrypted_value = str(stored_record.get("encrypted_value") or "").strip() if stored_record else ""
                if encrypted_value:
                    decrypted_text = self.secret_service.decrypt(encrypted_value)
                    with tempfile.NamedTemporaryFile(
                        mode="w",
                        encoding="utf-8",
                        suffix=".txt",
                        prefix="supoclip-ytdlp-",
                        delete=False,
                    ) as temp_file:
                        temp_file.write(decrypted_text)
                        temp_path = Path(temp_file.name)
                    yield str(temp_path)
                    return

            fallback_path = (config.ytdlp_cookies_file or "").strip()
            if fallback_path and Path(fallback_path).is_file():
                yield fallback_path
            else:
                yield None
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    async def get_video_title_for_user(self, url: str, user_id: Optional[str]) -> str:
        async with self._resolved_youtube_cookie_file(user_id) as cookie_file_path:
            return await self.video_service.get_video_title(url, cookie_file_path=cookie_file_path)

    async def resolve_video_path_for_user(
        self,
        *,
        url: str,
        source_type: str,
        user_id: Optional[str],
        progress_callback: Optional[callable] = None,
        source_options: Optional[Dict[str, Any]] = None,
    ) -> Path:
        async with self._resolved_youtube_cookie_file(user_id) as cookie_file_path:
            return await self.video_service.resolve_video_path(
                url=url,
                source_type=source_type,
                progress_callback=progress_callback,
                cookie_file_path=cookie_file_path,
                force_redownload=bool((source_options or {}).get("force_redownload")),
            )

    async def get_user_youtube_cookie_status(self, user_id: str) -> Dict[str, Any]:
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")
        stored_record = await self.task_repo.get_user_youtube_cookies(self.db, user_id)
        has_saved = bool(stored_record)
        has_env_fallback = self._has_env_youtube_cookie_fallback()
        return {
            "has_youtube_cookies": has_saved,
            "youtube_cookies_updated_at": stored_record.get("updated_at") if stored_record else None,
            "youtube_cookies_filename": stored_record.get("filename") if stored_record else None,
            "youtube_cookie_source": "saved" if has_saved else ("env" if has_env_fallback else "none"),
            "has_youtube_cookie_env_fallback": has_env_fallback,
        }

    async def save_user_youtube_cookies(self, user_id: str, filename: str, cookies_text: str) -> Dict[str, Any]:
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")
        encrypted_value = self.secret_service.encrypt(cookies_text)
        await self.task_repo.set_user_youtube_cookies(self.db, user_id, encrypted_value, filename)
        return await self.get_user_youtube_cookie_status(user_id)

    async def clear_user_youtube_cookies(self, user_id: str) -> Dict[str, Any]:
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")
        await self.task_repo.clear_user_youtube_cookies(self.db, user_id)
        return await self.get_user_youtube_cookie_status(user_id)

    async def create_task_with_source(
        self,
        user_id: str,
        url: str,
        title: Optional[str] = None,
        font_family: str = "TikTokSans-Regular",
        font_size: int = 24,
        font_color: str = "#FFFFFF",
        subtitle_style: Optional[Dict[str, Any]] = None,
        transitions_enabled: bool = False,
        transcription_provider: str = "local",
        ai_provider: str = "openai",
        ai_model: Optional[str] = None,
        ai_focus_tags: Optional[List[str]] = None,
        review_before_render_enabled: bool = True,
        timeline_editor_enabled: bool = True,
        processing_profile: str = "balanced",
        runtime_info_json: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Create a new task with associated source.
        Returns the task ID.
        """
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")

        source_type = self.video_service.determine_source_type(url)

        if not title:
            if source_type == "youtube":
                title = await self.get_video_title_for_user(url, user_id=user_id)
            else:
                title = "Uploaded Video"

        source_id = await self.source_repo.create_source(
            self.db,
            source_type=source_type,
            title=title,
            url=url,
        )

        task_id = await self.task_repo.create_task(
            self.db,
            user_id=user_id,
            source_id=source_id,
            status="queued",
            font_family=font_family,
            font_size=font_size,
            font_color=font_color,
            subtitle_style=subtitle_style,
            transitions_enabled=transitions_enabled,
            transcription_provider=transcription_provider,
            ai_provider=ai_provider,
            ai_focus_tags=ai_focus_tags,
            processing_profile=self._normalize_processing_profile(processing_profile),
            runtime_info_json=runtime_info_json,
            stage_checkpoint="queued",
            retryable_from_stages=[],
            review_before_render_enabled=review_before_render_enabled,
            timeline_editor_enabled=timeline_editor_enabled,
        )

        logger.info(f"Created task {task_id} for user {user_id}")
        return task_id

    @staticmethod
    def _env_ai_key_for_provider(provider: str) -> Optional[str]:
        normalized_provider = (provider or "").strip().lower()
        if normalized_provider == "openai":
            return (config.openai_api_key or "").strip() or None
        if normalized_provider == "google":
            return (config.google_api_key or "").strip() or None
        if normalized_provider == "anthropic":
            return (config.anthropic_api_key or "").strip() or None
        if normalized_provider == "zai":
            return (config.zai_api_key or "").strip() or None
        return None

    @staticmethod
    def _resolve_ai_model(provider: str, requested_model: Optional[str]) -> str:
        normalized_provider = (provider or "").strip().lower()
        if requested_model and requested_model.strip():
            return requested_model.strip()
        return DEFAULT_AI_MODELS.get(normalized_provider, DEFAULT_AI_MODELS["openai"])

    @staticmethod
    def _normalize_zai_routing_mode(value: Optional[str]) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in SUPPORTED_ZAI_ROUTING_MODES:
            return "auto"
        return normalized

    @staticmethod
    def _normalize_base_url(value: Optional[str]) -> Optional[str]:
        raw = str(value or "").strip()
        if not raw:
            return None
        if not raw.startswith(("http://", "https://")):
            raw = f"http://{raw}"
        return raw.rstrip("/")

    @classmethod
    def _normalize_ollama_base_url(cls, value: Optional[str]) -> str:
        normalized = cls._normalize_base_url(value)
        if not normalized:
            raise ValueError("Ollama server URL is required")
        return normalized

    @staticmethod
    def _normalize_ollama_profile_name(value: Optional[str]) -> Optional[str]:
        normalized = (value or "").strip().lower()
        return normalized or None

    @staticmethod
    def _normalize_ollama_auth_mode(value: Optional[str]) -> str:
        normalized = (value or "none").strip().lower()
        if normalized not in SUPPORTED_OLLAMA_AUTH_MODES:
            raise ValueError(f"Unsupported Ollama auth mode: {value}")
        return normalized

    @staticmethod
    def _normalize_ollama_auth_header_name(value: Optional[str]) -> Optional[str]:
        header_name = (value or "").strip()
        if not header_name:
            return None
        if ":" in header_name or "\n" in header_name or "\r" in header_name:
            raise ValueError("Invalid Ollama auth header name")
        return header_name

    @staticmethod
    def _normalize_ollama_request_control(
        value: Optional[int],
        *,
        field_name: str,
        minimum: int,
        maximum: int,
    ) -> Optional[int]:
        if value is None:
            return None
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be an integer") from exc
        if normalized < minimum or normalized > maximum:
            raise ValueError(f"{field_name} must be between {minimum} and {maximum}")
        return normalized

    def _env_ollama_request_controls(self) -> Dict[str, int]:
        timeout_seconds = self._normalize_ollama_request_control(
            getattr(config, "ollama_timeout_seconds", DEFAULT_OLLAMA_TIMEOUT_SECONDS),
            field_name="OLLAMA_TIMEOUT_SECONDS",
            minimum=MIN_OLLAMA_TIMEOUT_SECONDS,
            maximum=MAX_OLLAMA_TIMEOUT_SECONDS,
        ) or DEFAULT_OLLAMA_TIMEOUT_SECONDS
        max_retries = self._normalize_ollama_request_control(
            getattr(config, "ollama_max_retries", DEFAULT_OLLAMA_MAX_RETRIES),
            field_name="OLLAMA_MAX_RETRIES",
            minimum=MIN_OLLAMA_MAX_RETRIES,
            maximum=MAX_OLLAMA_MAX_RETRIES,
        ) if getattr(config, "ollama_max_retries", None) is not None else DEFAULT_OLLAMA_MAX_RETRIES
        retry_backoff_ms = self._normalize_ollama_request_control(
            getattr(config, "ollama_retry_backoff_ms", DEFAULT_OLLAMA_RETRY_BACKOFF_MS),
            field_name="OLLAMA_RETRY_BACKOFF_MS",
            minimum=MIN_OLLAMA_RETRY_BACKOFF_MS,
            maximum=MAX_OLLAMA_RETRY_BACKOFF_MS,
        ) if getattr(config, "ollama_retry_backoff_ms", None) is not None else DEFAULT_OLLAMA_RETRY_BACKOFF_MS
        return {
            "timeout_seconds": timeout_seconds,
            "max_retries": max_retries if max_retries is not None else DEFAULT_OLLAMA_MAX_RETRIES,
            "retry_backoff_ms": (
                retry_backoff_ms if retry_backoff_ms is not None else DEFAULT_OLLAMA_RETRY_BACKOFF_MS
            ),
        }

    @staticmethod
    def _resolve_ollama_model_request_preset(model_name: Optional[str]) -> Dict[str, Any]:
        normalized_model = str(model_name or "").strip().lower()
        if not normalized_model:
            return {}
        for needle, preset in OLLAMA_MODEL_REQUEST_PRESETS:
            if needle in normalized_model:
                return dict(preset)
        return {}

    @classmethod
    def _apply_ollama_model_request_preset(
        cls,
        *,
        timeout_seconds: int,
        max_retries: int,
        retry_backoff_ms: int,
        model_name: Optional[str],
    ) -> Tuple[Dict[str, int], Dict[str, Any]]:
        preset = cls._resolve_ollama_model_request_preset(model_name)
        effective_timeout = timeout_seconds
        effective_retries = max_retries
        effective_backoff = retry_backoff_ms

        preset_timeout = preset.get("timeout_seconds")
        if isinstance(preset_timeout, int):
            effective_timeout = max(effective_timeout, preset_timeout)
        preset_retries = preset.get("max_retries")
        if isinstance(preset_retries, int):
            effective_retries = max(effective_retries, preset_retries)
        preset_backoff = preset.get("retry_backoff_ms")
        if isinstance(preset_backoff, int):
            effective_backoff = max(effective_backoff, preset_backoff)

        normalized_timeout = cls._normalize_ollama_request_control(
            effective_timeout,
            field_name="ollama_timeout_seconds",
            minimum=MIN_OLLAMA_TIMEOUT_SECONDS,
            maximum=MAX_OLLAMA_TIMEOUT_SECONDS,
        ) or DEFAULT_OLLAMA_TIMEOUT_SECONDS
        normalized_retries = cls._normalize_ollama_request_control(
            effective_retries,
            field_name="ollama_max_retries",
            minimum=MIN_OLLAMA_MAX_RETRIES,
            maximum=MAX_OLLAMA_MAX_RETRIES,
        )
        normalized_backoff = cls._normalize_ollama_request_control(
            effective_backoff,
            field_name="ollama_retry_backoff_ms",
            minimum=MIN_OLLAMA_RETRY_BACKOFF_MS,
            maximum=MAX_OLLAMA_RETRY_BACKOFF_MS,
        )

        return (
            {
                "timeout_seconds": normalized_timeout,
                "max_retries": (
                    normalized_retries if normalized_retries is not None else DEFAULT_OLLAMA_MAX_RETRIES
                ),
                "retry_backoff_ms": (
                    normalized_backoff if normalized_backoff is not None else DEFAULT_OLLAMA_RETRY_BACKOFF_MS
                ),
            },
            preset,
        )

    @classmethod
    def _build_ollama_request_options(
        cls,
        *,
        profile_name: Optional[str],
        auth_mode: Optional[str],
        auth_headers: Dict[str, str],
        timeout_seconds: int,
        max_retries: int,
        retry_backoff_ms: int,
        model_name: Optional[str],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        effective_controls, preset = cls._apply_ollama_model_request_preset(
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            retry_backoff_ms=retry_backoff_ms,
            model_name=model_name,
        )
        options: Dict[str, Any] = {
            "ollama_profile": profile_name,
            "ollama_auth_mode": auth_mode,
            "ollama_auth_headers": dict(auth_headers or {}),
            "ollama_timeout_seconds": int(effective_controls["timeout_seconds"]),
            "ollama_max_retries": int(effective_controls["max_retries"]),
            "ollama_retry_backoff_ms": int(effective_controls["retry_backoff_ms"]),
        }
        if "temperature" in preset:
            options["ollama_temperature"] = float(preset["temperature"])
        if "think" in preset:
            options["ollama_think"] = preset["think"]
        return options, preset

    async def _resolve_ollama_request_controls(
        self,
        *,
        user_id: Optional[str],
        requested_timeout_seconds: Optional[int] = None,
        requested_max_retries: Optional[int] = None,
        requested_retry_backoff_ms: Optional[int] = None,
    ) -> Dict[str, int]:
        resolved = self._env_ollama_request_controls()

        if user_id:
            stored = await self.task_repo.get_user_ollama_request_controls(self.db, user_id)
            stored_timeout = self._normalize_ollama_request_control(
                stored.get("timeout_seconds"),
                field_name="default_ollama_timeout_seconds",
                minimum=MIN_OLLAMA_TIMEOUT_SECONDS,
                maximum=MAX_OLLAMA_TIMEOUT_SECONDS,
            )
            stored_retries = self._normalize_ollama_request_control(
                stored.get("max_retries"),
                field_name="default_ollama_max_retries",
                minimum=MIN_OLLAMA_MAX_RETRIES,
                maximum=MAX_OLLAMA_MAX_RETRIES,
            )
            stored_backoff = self._normalize_ollama_request_control(
                stored.get("retry_backoff_ms"),
                field_name="default_ollama_retry_backoff_ms",
                minimum=MIN_OLLAMA_RETRY_BACKOFF_MS,
                maximum=MAX_OLLAMA_RETRY_BACKOFF_MS,
            )
            if stored_timeout is not None:
                resolved["timeout_seconds"] = stored_timeout
            if stored_retries is not None:
                resolved["max_retries"] = stored_retries
            if stored_backoff is not None:
                resolved["retry_backoff_ms"] = stored_backoff

        override_timeout = self._normalize_ollama_request_control(
            requested_timeout_seconds,
            field_name="timeout_seconds",
            minimum=MIN_OLLAMA_TIMEOUT_SECONDS,
            maximum=MAX_OLLAMA_TIMEOUT_SECONDS,
        )
        override_retries = self._normalize_ollama_request_control(
            requested_max_retries,
            field_name="max_retries",
            minimum=MIN_OLLAMA_MAX_RETRIES,
            maximum=MAX_OLLAMA_MAX_RETRIES,
        )
        override_backoff = self._normalize_ollama_request_control(
            requested_retry_backoff_ms,
            field_name="retry_backoff_ms",
            minimum=MIN_OLLAMA_RETRY_BACKOFF_MS,
            maximum=MAX_OLLAMA_RETRY_BACKOFF_MS,
        )
        if override_timeout is not None:
            resolved["timeout_seconds"] = override_timeout
        if override_retries is not None:
            resolved["max_retries"] = override_retries
        if override_backoff is not None:
            resolved["retry_backoff_ms"] = override_backoff
        return resolved

    def _resolve_ollama_auth_headers(
        self,
        *,
        auth_mode: str,
        auth_header_name: Optional[str],
        auth_secret_value: Optional[str],
    ) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if auth_mode == "none":
            return headers
        token = (auth_secret_value or "").strip()
        if not token:
            raise ValueError(f"Ollama auth token is missing for auth mode '{auth_mode}'")
        if auth_mode == "bearer":
            headers["Authorization"] = f"Bearer {token}"
            return headers
        header_name = self._normalize_ollama_auth_header_name(auth_header_name)
        if not header_name:
            raise ValueError("auth_header_name is required for custom_header mode")
        headers[header_name] = token
        return headers

    async def _resolve_effective_ollama_settings(
        self,
        *,
        user_id: Optional[str],
        requested_profile: Optional[str] = None,
        requested_base_url: Optional[str] = None,
        requested_timeout_seconds: Optional[int] = None,
        requested_max_retries: Optional[int] = None,
        requested_retry_backoff_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        requested = self._normalize_base_url(requested_base_url)
        controls = await self._resolve_ollama_request_controls(
            user_id=user_id,
            requested_timeout_seconds=requested_timeout_seconds,
            requested_max_retries=requested_max_retries,
            requested_retry_backoff_ms=requested_retry_backoff_ms,
        )
        if requested:
            return {
                "profile_name": None,
                "base_url": requested,
                "auth_headers": {},
                "auth_mode": "none",
                "has_auth_secret": False,
                **controls,
            }

        resolved_profile_name = self._normalize_ollama_profile_name(requested_profile)
        profile_record: Optional[Dict[str, Any]] = None
        if user_id:
            if resolved_profile_name:
                profile_record = await self.task_repo.get_user_ollama_profile(
                    self.db,
                    user_id,
                    resolved_profile_name,
                    include_secret=True,
                )
                if profile_record and not bool(profile_record.get("enabled", True)):
                    raise ValueError(f"Ollama profile is disabled: {resolved_profile_name}")
                if not profile_record:
                    raise ValueError(f"Ollama profile not found: {resolved_profile_name}")
            else:
                default_profile = await self.task_repo.get_user_default_ollama_profile(self.db, user_id)
                if default_profile:
                    profile_record = await self.task_repo.get_user_ollama_profile(
                        self.db,
                        user_id,
                        default_profile,
                        include_secret=True,
                    )
                if not profile_record:
                    profiles = await self.task_repo.list_user_ollama_profiles(self.db, user_id)
                    enabled_profiles = [profile for profile in profiles if profile.get("enabled")]
                    if enabled_profiles:
                        first_profile_name = str(enabled_profiles[0]["profile_name"])
                        profile_record = await self.task_repo.get_user_ollama_profile(
                            self.db,
                            user_id,
                            first_profile_name,
                            include_secret=True,
                        )

        if profile_record:
            auth_mode = self._normalize_ollama_auth_mode(str(profile_record.get("auth_mode") or "none"))
            decrypted_secret: Optional[str] = None
            encrypted_secret = profile_record.get("auth_secret_encrypted")
            if encrypted_secret:
                decrypted_secret = self.secret_service.decrypt(str(encrypted_secret))
            auth_headers = self._resolve_ollama_auth_headers(
                auth_mode=auth_mode,
                auth_header_name=profile_record.get("auth_header_name"),
                auth_secret_value=decrypted_secret,
            )
            return {
                "profile_name": str(profile_record.get("profile_name") or ""),
                "base_url": self._normalize_ollama_base_url(profile_record.get("base_url")),
                "auth_headers": auth_headers,
                "auth_mode": auth_mode,
                "has_auth_secret": bool(profile_record.get("has_auth_secret")),
                **controls,
            }

        if user_id:
            saved = await self.task_repo.get_user_ollama_base_url(self.db, user_id)
            normalized_saved = self._normalize_base_url(saved)
            if normalized_saved:
                return {
                    "profile_name": None,
                    "base_url": normalized_saved,
                    "auth_headers": {},
                    "auth_mode": "none",
                    "has_auth_secret": False,
                    **controls,
                }

        env_fallback = self._normalize_base_url(config.ollama_base_url)
        return {
            "profile_name": None,
            "base_url": env_fallback or DEFAULT_OLLAMA_BASE_URL,
            "auth_headers": {},
            "auth_mode": "none",
            "has_auth_secret": False,
            **controls,
        }

    async def _resolve_effective_ollama_base_url(
        self,
        user_id: Optional[str],
        requested_base_url: Optional[str] = None,
    ) -> str:
        settings = await self._resolve_effective_ollama_settings(
            user_id=user_id,
            requested_base_url=requested_base_url,
        )
        return str(settings["base_url"])

    @staticmethod
    def _normalize_text_for_compare(value: Optional[str]) -> str:
        return " ".join((value or "").split()).strip().lower()

    @staticmethod
    def _clamp_review_score(value: Any) -> float:
        return round(max(0.0, min(1.0, float(value or 0.0))), 4)

    @staticmethod
    def _normalize_framing_mode_override(value: Any) -> str:
        normalized = str(value or "auto").strip().lower()
        if normalized == "disable_face_crop":
            return "fixed_position"
        if normalized not in SUPPORTED_FRAMING_MODE_OVERRIDES:
            return "auto"
        return normalized

    @staticmethod
    def _normalize_face_detection_mode(value: Any) -> str:
        normalized = str(value or "balanced").strip().lower()
        if normalized == "center_only":
            return "balanced"
        if normalized not in SUPPORTED_FACE_DETECTION_MODES:
            return "balanced"
        return normalized

    @staticmethod
    def _normalize_fallback_crop_position(value: Any) -> str:
        normalized = str(value or "center").strip().lower()
        if normalized not in SUPPORTED_FALLBACK_CROP_POSITIONS:
            return "center"
        return normalized

    @staticmethod
    def _normalize_face_anchor_profile(value: Any) -> str:
        normalized = str(value or "auto").strip().lower()
        if normalized not in SUPPORTED_FACE_ANCHOR_PROFILES:
            return "auto"
        return normalized

    @classmethod
    def _resolve_effective_default_framing_mode(
        cls,
        default_framing_mode: Any,
        face_detection_mode: Any,
    ) -> str:
        return cls._normalize_framing_mode_override(default_framing_mode)

    async def _get_effective_user_video_preferences(
        self,
        user_id: Optional[str],
        task_video_overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not user_id:
            preferences = {
                "review_before_render_enabled": True,
                "timeline_editor_enabled": True,
                "default_processing_profile": "balanced",
                "default_framing_mode": "auto",
                "default_face_detection_mode": "balanced",
                "default_fallback_crop_position": "center",
                "default_face_anchor_profile": "auto",
                "effective_default_framing_mode": "auto",
            }
        else:
            preferences = await self.task_repo.get_user_default_video_preferences(self.db, user_id)

        if isinstance(task_video_overrides, dict):
            preferences = {
                **preferences,
                "default_framing_mode": task_video_overrides.get("default_framing_mode", preferences.get("default_framing_mode")),
                "default_face_detection_mode": task_video_overrides.get("face_detection_mode", preferences.get("default_face_detection_mode")),
                "default_fallback_crop_position": task_video_overrides.get("fallback_crop_position", preferences.get("default_fallback_crop_position")),
                "default_face_anchor_profile": task_video_overrides.get("face_anchor_profile", preferences.get("default_face_anchor_profile")),
            }
        raw_detection_mode = str(preferences.get("default_face_detection_mode") or "balanced").strip().lower()
        default_framing_mode = self._normalize_framing_mode_override(preferences.get("default_framing_mode"))
        face_detection_mode = self._normalize_face_detection_mode(raw_detection_mode)
        fallback_crop_position = self._normalize_fallback_crop_position(
            preferences.get("default_fallback_crop_position")
        )
        face_anchor_profile = self._normalize_face_anchor_profile(
            preferences.get("default_face_anchor_profile")
        )
        effective_default_framing_mode = self._resolve_effective_default_framing_mode(
            "fixed_position" if raw_detection_mode == "center_only" else default_framing_mode,
            face_detection_mode,
        )
        if raw_detection_mode == "center_only":
            fallback_crop_position = "center"
        if face_anchor_profile == "auto" and fallback_crop_position == "left_center":
            face_anchor_profile = "left_or_center"
        elif face_anchor_profile == "auto" and fallback_crop_position == "right_center":
            face_anchor_profile = "right_or_center"
        return {
            **preferences,
            "default_processing_profile": self._normalize_processing_profile(
                preferences.get("default_processing_profile")
            ),
            "default_framing_mode": default_framing_mode,
            "default_face_detection_mode": face_detection_mode,
            "default_fallback_crop_position": fallback_crop_position,
            "default_face_anchor_profile": face_anchor_profile,
            "effective_default_framing_mode": effective_default_framing_mode,
        }

    @staticmethod
    def _normalize_processing_profile(value: Any) -> str:
        normalized = str(value or "balanced").strip().lower()
        if normalized not in SUPPORTED_PROCESSING_PROFILES:
            return "balanced"
        return normalized

    @staticmethod
    def _normalize_stage_checkpoint(value: Any) -> str:
        normalized = str(value or "queued").strip().lower()
        supported = {"queued", "started", "downloaded", "transcribed", "analyzed", "review_approved", "completed", "failed"}
        if normalized not in supported:
            return "queued"
        return normalized

    @staticmethod
    def _merge_runtime_info(base: Optional[Dict[str, Any]], update: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        merged = dict(base or {})
        for key, value in (update or {}).items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = TaskService._merge_runtime_info(merged.get(key), value)
            else:
                merged[key] = value
        return merged

    @staticmethod
    def _runtime_time_ms() -> int:
        return int(time.time() * 1000)

    @staticmethod
    def _coerce_runtime_time_ms(value: Any) -> Optional[int]:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            coerced = int(value)
            return coerced if coerced >= 0 else None
        return None

    @staticmethod
    def _coerce_runtime_seconds(value: Any) -> float:
        if isinstance(value, bool):
            return 0.0
        if isinstance(value, (int, float)):
            return max(0.0, float(value))
        return 0.0

    @classmethod
    def _open_processing_runtime_window(
        cls,
        runtime_info: Optional[Dict[str, Any]],
        *,
        started_at_ms: int,
        render_from_drafts: bool,
    ) -> Dict[str, Any]:
        existing = dict(runtime_info or {})
        update: Dict[str, Any] = {
            "active_processing_seconds": cls._coerce_runtime_seconds(existing.get("active_processing_seconds")),
        }
        if cls._coerce_runtime_time_ms(existing.get("processing_window_started_at_ms")) is None:
            update["processing_window_started_at_ms"] = started_at_ms

        if render_from_drafts:
            if cls._coerce_runtime_time_ms(existing.get("review_started_at_ms")) is not None:
                update["review_completed_at_ms"] = (
                    cls._coerce_runtime_time_ms(existing.get("review_completed_at_ms")) or started_at_ms
                )
            if cls._coerce_runtime_time_ms(existing.get("render_started_at_ms")) is None:
                update["render_started_at_ms"] = started_at_ms
        else:
            if cls._coerce_runtime_time_ms(existing.get("analysis_started_at_ms")) is None:
                update["analysis_started_at_ms"] = started_at_ms
        return update

    @classmethod
    def _close_processing_runtime_window(
        cls,
        runtime_info: Optional[Dict[str, Any]],
        *,
        ended_at_ms: int,
        final_status: str,
        render_from_drafts: bool,
    ) -> Dict[str, Any]:
        existing = dict(runtime_info or {})
        started_at_ms = cls._coerce_runtime_time_ms(existing.get("processing_window_started_at_ms"))
        total_active_seconds = cls._coerce_runtime_seconds(existing.get("active_processing_seconds"))
        if started_at_ms is not None:
            total_active_seconds += max(0.0, (ended_at_ms - started_at_ms) / 1000.0)

        update: Dict[str, Any] = {
            "active_processing_seconds": round(total_active_seconds, 3),
            "processing_window_started_at_ms": None,
        }

        if final_status == "awaiting_review":
            update["analysis_completed_at_ms"] = ended_at_ms
            update["review_started_at_ms"] = ended_at_ms
            update["review_completed_at_ms"] = None
        elif final_status == "completed":
            if render_from_drafts:
                update["render_completed_at_ms"] = ended_at_ms
            else:
                update["analysis_completed_at_ms"] = ended_at_ms

        return update

    @staticmethod
    def _compute_retryable_stages(
        checkpoint: str,
        *,
        review_before_render_enabled: bool,
        has_drafts: bool,
        has_generated_clips: bool,
    ) -> List[str]:
        allowed: List[str] = []
        normalized_checkpoint = TaskService._normalize_stage_checkpoint(checkpoint)
        if normalized_checkpoint not in RETRYABLE_STAGE_ORDER:
            return allowed
        for stage in RETRYABLE_STAGE_ORDER:
            if RETRYABLE_STAGE_ORDER.index(stage) <= RETRYABLE_STAGE_ORDER.index(normalized_checkpoint):
                allowed.append(stage)
        if not has_drafts and "analyzed" in allowed:
            allowed.remove("analyzed")
        if not (review_before_render_enabled and has_drafts) and "review_approved" in allowed:
            allowed.remove("review_approved")
        if has_generated_clips and "review_approved" not in allowed and review_before_render_enabled and has_drafts:
            allowed.append("review_approved")
        return allowed

    @classmethod
    def _classify_failure(cls, error: Exception) -> Tuple[str, str]:
        message = str(error or "").strip()
        lowered = message.lower()
        if any(marker in lowered for marker in CORRUPT_AUDIO_FAILURE_MARKERS):
            code = "transcription"
        elif "download" in lowered or "youtube" in lowered or "source url" in lowered:
            code = "download"
        elif "transcrib" in lowered or "assemblyai" in lowered or "whisper" in lowered:
            code = "transcription"
        elif "ollama" in lowered or "openai" in lowered or "anthropic" in lowered or "google" in lowered or "glm" in lowered or "analysis" in lowered:
            code = "ai_analysis"
        elif "draft" in lowered or "overlap" in lowered or "selected draft clip" in lowered:
            code = "draft_validation"
        elif "render" in lowered or "subtitle" in lowered or "clip" in lowered:
            code = "render"
        elif "permission" in lowered or "disk" in lowered or "write" in lowered or "save" in lowered:
            code = "storage"
        else:
            code = "system"
        if code == "download" and (
            "not a bot" in lowered
            or "sign-in verification" in lowered
            or "cookies.txt" in lowered
            or "upload a valid youtube cookies" in lowered
            or "shared server fallback" in lowered
        ):
            return (
                code,
                "YouTube requested sign-in verification. Upload a YouTube cookies.txt file in Settings > Transcription, then retry from download.",
            )
        if code == "transcription" and any(marker in lowered for marker in CORRUPT_AUDIO_FAILURE_MARKERS):
            return (
                code,
                "The video downloaded, but its audio stream appears damaged. Retry once, and if it keeps failing upload the source video directly instead of the YouTube link.",
            )
        return code, FAILURE_HINTS[code]

    def _build_draft_selection_rationale(self, draft: Dict[str, Any]) -> Dict[str, Any]:
        metadata = draft.get("framing_metadata_json") if isinstance(draft.get("framing_metadata_json"), dict) else {}
        transcript_relevance = round(float(draft.get("relevance_score") or 0.0), 3)
        review_score = round(float(draft.get("review_score") or transcript_relevance), 3)
        framing_quality = str(metadata.get("detection_state") or "none")
        if framing_quality not in {"strong", "weak", "none"}:
            framing_quality = "none"
        hook_score = round(max(0.0, min(1.0, review_score - float(draft.get("feedback_score_adjustment") or 0.0))), 3)
        feedback = draft.get("feedback_signals_json") if isinstance(draft.get("feedback_signals_json"), dict) else {}
        review_adjustments: List[str] = []
        if feedback.get("created_by_user"):
            review_adjustments.append("manual clip")
        if feedback.get("timing_changed"):
            review_adjustments.append("trimmed")
        if feedback.get("text_edited"):
            review_adjustments.append("subtitle edited")
        if feedback.get("deselected"):
            review_adjustments.append("deselected")
        return {
            "transcript_relevance": transcript_relevance,
            "framing_quality": framing_quality,
            "hook_score": hook_score,
            "review_adjustments": review_adjustments,
        }

    @staticmethod
    def _build_preview_strip_url(task_id: str, draft_id: str) -> str:
        return f"/tasks/{task_id}/draft-clips/{draft_id}/preview-strip"

    def _task_artifact_dir(self, task_id: str) -> Path:
        return Path(config.temp_dir) / "task-artifacts" / task_id

    def _draft_preview_strip_dir(self, task_id: str) -> Path:
        return self._task_artifact_dir(task_id) / "draft-previews"

    def _draft_preview_strip_path(self, task_id: str, draft_id: str) -> Path:
        return self._draft_preview_strip_dir(task_id) / f"{draft_id}.jpg"

    def _reset_draft_preview_strip_dir(self, task_id: str) -> None:
        preview_dir = self._draft_preview_strip_dir(task_id)
        if preview_dir.exists():
            shutil.rmtree(preview_dir, ignore_errors=True)
        preview_dir.mkdir(parents=True, exist_ok=True)

    def _attach_draft_view_fields(self, task_id: str, drafts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for draft in drafts:
            draft["preview_url"] = self._build_preview_strip_url(task_id, str(draft["id"]))
            draft["selection_rationale"] = self._build_draft_selection_rationale(draft)
        return drafts

    @staticmethod
    def _default_worker_runtime_info() -> Dict[str, Any]:
        return {
            "supported_device_preferences": ["auto", "cpu", "gpu"],
            "cuda_available": False,
            "gpu_count": 0,
            "gpu_devices": [],
            "gpu_device_name": None,
            "probe_source": "worker_heartbeat_unavailable",
            "runtime_scope": "worker_process",
            "cache_dir": None,
            "triton_package_installed": False,
            "cuda_toolkit_ptxas_available": False,
            "cuda_toolkit_ptxas_path": None,
            "triton_timing_kernels_enabled": False,
            "triton_fallback_reason": "No active worker heartbeat available",
            "triton_probe_source": "none",
        }

    @staticmethod
    def _select_worker_runtime_from_heartbeats(worker_heartbeats: List[Dict[str, Any]]) -> Dict[str, Any]:
        preferred_queue_names = [
            config.arq_local_gpu_queue_name,
            config.arq_local_queue_name,
            config.arq_assembly_queue_name,
        ]
        for queue_name in preferred_queue_names:
            for worker in worker_heartbeats:
                if str(worker.get("queue_name") or "") != queue_name:
                    continue
                runtime = worker.get("runtime")
                if not isinstance(runtime, dict):
                    continue
                selected = dict(runtime)
                selected["heartbeat_queue_name"] = queue_name
                selected["heartbeat_worker_name"] = worker.get("worker_name")
                selected["heartbeat_timestamp"] = worker.get("timestamp")
                selected["runtime_scope"] = str(selected.get("runtime_scope") or "worker_process")
                return selected
        return TaskService._default_worker_runtime_info()

    @staticmethod
    async def _read_worker_heartbeats(pool: Any) -> List[Dict[str, Any]]:
        worker_heartbeats: List[Dict[str, Any]] = []
        async for raw_key in pool.scan_iter(match="supoclip:worker-heartbeat:*"):
            key = raw_key.decode("utf-8") if isinstance(raw_key, bytes) else str(raw_key)
            payload = await pool.get(key)
            if not payload:
                continue
            try:
                parsed = json.loads(payload)
            except Exception:
                parsed = {"raw": payload}
            parsed["key"] = key
            worker_heartbeats.append(parsed)
        worker_heartbeats.sort(key=lambda item: str(item.get("queue_name") or item.get("worker_name") or ""))
        return worker_heartbeats

    async def get_worker_runtime_snapshot(self) -> Dict[str, Any]:
        from ..workers.job_queue import JobQueue

        pool = await JobQueue.get_pool()
        worker_heartbeats = await self._read_worker_heartbeats(pool)
        return {
            "workers": worker_heartbeats,
            "local_whisper_runtime": self._select_worker_runtime_from_heartbeats(worker_heartbeats),
        }

    async def _persist_draft_preview_strips(
        self,
        task_id: str,
        drafts: List[Dict[str, Any]],
        *,
        video_path: Path,
        reset_existing: bool = False,
    ) -> None:
        if not drafts:
            return
        if reset_existing:
            self._reset_draft_preview_strip_dir(task_id)
        else:
            self._draft_preview_strip_dir(task_id).mkdir(parents=True, exist_ok=True)

        for draft in drafts:
            draft_id = str(draft.get("id") or "").strip()
            if not draft_id:
                continue
            output_path = self._draft_preview_strip_path(task_id, draft_id)
            try:
                await asyncio.to_thread(
                    self._generate_preview_strip,
                    video_path=video_path,
                    start_time=str(draft.get("start_time") or "00:00"),
                    end_time=str(draft.get("end_time") or "00:00"),
                    output_path=output_path,
                )
            except Exception as error:
                logger.warning(
                    "Failed to persist draft preview strip for task %s draft %s: %s",
                    task_id,
                    draft_id,
                    error,
                )

    async def _refresh_draft_preview_strips(
        self,
        task_id: str,
        draft_ids: List[str],
    ) -> None:
        normalized_ids = [str(draft_id).strip() for draft_id in draft_ids if str(draft_id).strip()]
        if not normalized_ids:
            return

        task = await self.task_repo.get_task_by_id(self.db, task_id)
        if not task:
            logger.warning("Skipping draft preview refresh for missing task %s", task_id)
            return

        source_url = str(task.get("source_url") or "").strip()
        source_type = str(task.get("source_type") or "").strip()
        if not source_url or not source_type:
            logger.warning("Skipping draft preview refresh for task %s because source metadata is missing", task_id)
            return

        try:
            video_path = await self.resolve_video_path_for_user(
                url=source_url,
                source_type=source_type,
                user_id=str(task.get("user_id") or ""),
            )
        except Exception as error:
            logger.warning("Failed to resolve source video for task %s draft preview refresh: %s", task_id, error)
            return

        draft_map = await self.draft_clip_repo.get_draft_map_by_task(self.db, task_id)
        drafts_to_refresh = [draft_map[draft_id] for draft_id in normalized_ids if draft_id in draft_map]
        await self._persist_draft_preview_strips(task_id, drafts_to_refresh, video_path=video_path)

    async def ensure_draft_preview_strip(
        self,
        task_id: str,
        draft: Dict[str, Any],
        *,
        source_url: str,
        source_type: str,
        force_regenerate: bool = False,
    ) -> Path:
        preview_path = self._draft_preview_strip_path(task_id, str(draft["id"]))
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        if preview_path.exists() and not force_regenerate:
            return preview_path

        video_path = await self.resolve_video_path_for_user(
            url=source_url,
            source_type=source_type,
            user_id=str(task.get("user_id") or ""),
        )
        await asyncio.to_thread(
            self._generate_preview_strip,
            video_path=video_path,
            start_time=str(draft.get("start_time") or "00:00"),
            end_time=str(draft.get("end_time") or "00:00"),
            output_path=preview_path,
        )
        return preview_path

    @classmethod
    def _generate_preview_strip(
        cls,
        *,
        video_path: Path,
        start_time: str,
        end_time: str,
        output_path: Path,
    ) -> None:
        import cv2  # type: ignore
        import numpy as np  # type: ignore

        start_seconds = cls._parse_timestamp_to_seconds_strict(start_time)
        end_seconds = cls._parse_timestamp_to_seconds_strict(end_time)
        duration = max(0.25, end_seconds - start_seconds)
        sample_offsets = (0.2, 0.5, 0.8)
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            raise ValueError(f"Unable to open source video for preview generation: {video_path}")

        frames = []
        try:
            for offset in sample_offsets:
                sample_seconds = start_seconds + (duration * offset)
                capture.set(cv2.CAP_PROP_POS_MSEC, max(0.0, sample_seconds) * 1000.0)
                ok, frame = capture.read()
                if not ok or frame is None:
                    continue
                height, width = frame.shape[:2]
                target_width = 320
                target_height = max(1, int(round((target_width / max(1, width)) * height)))
                resized = cv2.resize(frame, (target_width, target_height))
                label = cls._format_seconds_to_timestamp(sample_seconds)
                cv2.putText(
                    resized,
                    label,
                    (10, max(24, target_height - 16)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (255, 255, 255),
                    2,
                    cv2.LINE_AA,
                )
                frames.append(resized)
        finally:
            capture.release()

        if not frames:
            raise ValueError(f"Unable to extract preview frames from {video_path}")
        strip = np.concatenate(frames, axis=1)
        if not cv2.imwrite(str(output_path), strip):
            raise ValueError(f"Failed to write preview strip to {output_path}")

    @staticmethod
    def _extract_framing_score_adjustment(draft: Dict[str, Any]) -> float:
        metadata = draft.get("framing_metadata_json")
        if not isinstance(metadata, dict):
            return 0.0
        return round(max(-0.02, min(0.06, float(metadata.get("score_adjustment") or 0.0))), 4)

    @staticmethod
    def _resolve_review_auto_select_min_score(task_record: Optional[Dict[str, Any]]) -> Optional[float]:
        runtime_info = (
            task_record.get("runtime_info")
            if isinstance(task_record, dict) and isinstance(task_record.get("runtime_info"), dict)
            else {}
        )
        review_options = runtime_info.get("review_options") if isinstance(runtime_info.get("review_options"), dict) else {}
        raw_threshold_percent = review_options.get("auto_select_strong_face_min_score_percent")
        if raw_threshold_percent is None:
            return None
        try:
            threshold_percent = int(raw_threshold_percent)
        except (TypeError, ValueError):
            return None
        if threshold_percent < 0 or threshold_percent > 100:
            return None
        return max(
            MIN_REVIEW_AUTO_SELECT_MIN_SCORE,
            min(MAX_REVIEW_AUTO_SELECT_MIN_SCORE, threshold_percent / 100.0),
        )

    @staticmethod
    def _should_auto_select_review_draft(
        *,
        review_score: float,
        framing_metadata: Optional[Dict[str, Any]],
        min_review_score: Optional[float],
    ) -> bool:
        if min_review_score is None:
            return True
        detection_state = ""
        if isinstance(framing_metadata, dict):
            detection_state = str(framing_metadata.get("detection_state") or "").strip().lower()
        return detection_state == "strong" and float(review_score) >= float(min_review_score)

    def _build_draft_feedback_state(self, draft: Dict[str, Any]) -> Dict[str, Any]:
        base_score = self._clamp_review_score(
            float(draft.get("relevance_score") or 0.0) + self._extract_framing_score_adjustment(draft)
        )
        is_selected = bool(draft.get("is_selected", True))
        is_deleted = bool(draft.get("is_deleted", False))
        created_by_user = bool(draft.get("created_by_user", False))

        current_start = self._parse_timestamp_to_seconds_strict(str(draft.get("start_time") or "00:00"))
        current_end = self._parse_timestamp_to_seconds_strict(str(draft.get("end_time") or "00:00"))
        original_start = self._parse_timestamp_to_seconds_strict(
            str(draft.get("original_start_time") or draft.get("start_time") or "00:00")
        )
        original_end = self._parse_timestamp_to_seconds_strict(
            str(draft.get("original_end_time") or draft.get("end_time") or "00:00")
        )

        timing_shift_seconds = round(abs(current_start - original_start) + abs(current_end - original_end), 3)
        timing_changed = timing_shift_seconds > 1e-6
        text_edited = (
            self._normalize_text_for_compare(draft.get("edited_text"))
            != self._normalize_text_for_compare(draft.get("original_text"))
        )
        existing_feedback = draft.get("feedback_signals_json") if isinstance(draft.get("feedback_signals_json"), dict) else {}
        auto_selection_rule_excluded = bool(
            draft.get("auto_selection_rule_excluded", existing_feedback.get("auto_selection_rule_excluded", False))
        )
        user_selection_overridden = bool(
            draft.get("selection_changed_by_user", existing_feedback.get("user_selection_overridden", False))
        )
        is_user_deselected = not is_selected and (user_selection_overridden or not auto_selection_rule_excluded)
        is_auto_unselected = not is_selected and auto_selection_rule_excluded and not user_selection_overridden

        adjustment = 0.0
        if created_by_user:
            adjustment += REVIEW_MANUAL_CLIP_BONUS
        if timing_changed:
            adjustment += min(
                REVIEW_TIMING_EDIT_MAX_BONUS,
                REVIEW_TIMING_EDIT_BASE_BONUS + (timing_shift_seconds * REVIEW_TIMING_EDIT_PER_SECOND),
            )
        if text_edited:
            adjustment += REVIEW_TEXT_EDIT_BONUS
        if is_user_deselected:
            adjustment += REVIEW_DESELECT_PENALTY
        if is_deleted:
            adjustment += REVIEW_DELETE_PENALTY

        adjustment = round(adjustment, 4)
        return {
            "review_score": self._clamp_review_score(base_score + adjustment),
            "feedback_score_adjustment": adjustment,
            "feedback_signals_json": {
                "version": 1,
                "selected": is_selected,
                "deselected": is_user_deselected,
                "deleted": is_deleted,
                "created_by_user": created_by_user,
                "timing_changed": timing_changed,
                "timing_shift_seconds": timing_shift_seconds,
                "text_edited": text_edited,
                "auto_unselected": is_auto_unselected,
                "auto_selection_rule_excluded": auto_selection_rule_excluded,
                "user_selection_overridden": user_selection_overridden,
            },
        }

    @staticmethod
    def _parse_timestamp_to_seconds_strict(raw_timestamp: Any) -> float:
        value = str(raw_timestamp or "").strip()
        if not value:
            raise ValueError("timestamp is required")

        parts = value.split(":")
        if len(parts) == 2:
            minute_text, second_text = parts
            if not (minute_text.isdigit() and _TIMESTAMP_SECONDS_RE.match(second_text)):
                raise ValueError(f"Invalid timestamp format: {value}")
            minutes = int(minute_text)
            seconds = float(second_text)
            if seconds >= 60:
                raise ValueError(f"Invalid timestamp format: {value}")
            return minutes * 60 + seconds

        if len(parts) == 3:
            hour_text, minute_text, second_text = parts
            if not (hour_text.isdigit() and minute_text.isdigit() and _TIMESTAMP_SECONDS_RE.match(second_text)):
                raise ValueError(f"Invalid timestamp format: {value}")
            hours = int(hour_text)
            minutes = int(minute_text)
            seconds = float(second_text)
            if minutes > 59 or seconds >= 60:
                raise ValueError(f"Invalid timestamp format: {value}")
            return hours * 3600 + minutes * 60 + seconds

        raise ValueError(f"Invalid timestamp format: {value}")

    @staticmethod
    def _snap_to_timeline_increment(seconds: float) -> float:
        snapped = round(max(0.0, float(seconds)) / TIMELINE_INCREMENT_SECONDS) * TIMELINE_INCREMENT_SECONDS
        return round(max(0.0, snapped), 3)

    @classmethod
    def _format_seconds_to_timestamp(cls, seconds: float) -> str:
        snapped_seconds = cls._snap_to_timeline_increment(seconds)
        whole_seconds = int(snapped_seconds)
        fractional = snapped_seconds - whole_seconds
        hours = whole_seconds // 3600
        minutes = (whole_seconds % 3600) // 60
        remainder_seconds = whole_seconds % 60
        if abs(fractional - 0.5) < 1e-6:
            second_token = f"{remainder_seconds:02d}.5"
        else:
            second_token = f"{remainder_seconds:02d}"
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{second_token}"
        return f"{minutes:02d}:{second_token}"

    def _validate_clip_window(
        self,
        start_time: str,
        end_time: str,
    ) -> tuple[float, float, float]:
        start_seconds = self._snap_to_timeline_increment(self._parse_timestamp_to_seconds_strict(start_time))
        end_seconds = self._snap_to_timeline_increment(self._parse_timestamp_to_seconds_strict(end_time))
        if start_seconds >= end_seconds:
            raise ValueError("start_time must be less than end_time")
        duration_seconds = end_seconds - start_seconds
        if duration_seconds < DRAFT_MIN_DURATION_SECONDS or duration_seconds > DRAFT_MAX_DURATION_SECONDS:
            raise ValueError(
                f"Clip duration must be between {DRAFT_MIN_DURATION_SECONDS}s and {DRAFT_MAX_DURATION_SECONDS}s"
            )
        return (
            start_seconds,
            end_seconds,
            round(duration_seconds, 3),
        )

    def _validate_non_overlapping_draft_windows(self, drafts: List[Dict[str, Any]]) -> None:
        conflicts = self._collect_draft_overlap_conflicts(drafts)
        if conflicts:
            raise DraftOverlapError(conflicts)

    @staticmethod
    def _build_render_filename_prefix() -> str:
        return datetime.now().strftime("%Y%m%d_%H%M")

    def _collect_draft_overlap_conflicts(self, drafts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        windows: List[Dict[str, Any]] = []
        for draft in drafts:
            if draft.get("is_deleted"):
                continue
            draft_id = str(draft.get("id") or "")
            start_seconds = self._parse_timestamp_to_seconds_strict(str(draft.get("start_time") or ""))
            end_seconds = self._parse_timestamp_to_seconds_strict(str(draft.get("end_time") or ""))
            windows.append(
                {
                    "id": draft_id,
                    "clip_order": int(draft.get("clip_order") or 0),
                    "start_seconds": start_seconds,
                    "end_seconds": end_seconds,
                    "start_time": str(draft.get("start_time") or self._format_seconds_to_timestamp(start_seconds)),
                    "end_time": str(draft.get("end_time") or self._format_seconds_to_timestamp(end_seconds)),
                }
            )

        windows.sort(
            key=lambda item: (
                float(item["start_seconds"]),
                float(item["end_seconds"]),
                int(item["clip_order"]),
                str(item["id"]),
            )
        )
        for index, window in enumerate(windows, start=1):
            window["display_index"] = index
            window["display_label"] = (
                f"Clip {index} ({window['start_time']} -> {window['end_time']})"
            )

        conflicts: List[Dict[str, Any]] = []
        for index in range(1, len(windows)):
            previous = windows[index - 1]
            current = windows[index]
            if float(current["start_seconds"]) < (float(previous["end_seconds"]) - 1e-6):
                conflicts.append(
                    {
                        "left_id": previous["id"],
                        "right_id": current["id"],
                        "left_label": previous["display_label"],
                        "right_label": current["display_label"],
                        "left_start_time": previous["start_time"],
                        "left_end_time": previous["end_time"],
                        "right_start_time": current["start_time"],
                        "right_end_time": current["end_time"],
                    }
                )
        return conflicts

    @staticmethod
    def _extract_text_from_transcript_cache(video_path: Path, clip_start: float, clip_end: float) -> str:
        transcript_cache_path = video_path.with_suffix(".transcript_cache.json")
        if not transcript_cache_path.exists():
            return ""

        try:
            transcript_data = json.loads(transcript_cache_path.read_text(encoding="utf-8"))
        except Exception as cache_error:
            logger.warning("Failed to load transcript cache %s: %s", transcript_cache_path, cache_error)
            return ""

        if not transcript_data or not transcript_data.get("words"):
            return ""

        clip_start_ms = int(max(0.0, clip_start) * 1000)
        clip_end_ms = int(max(clip_start, clip_end) * 1000)
        matched_words: List[str] = []
        for word in transcript_data.get("words", []):
            word_text = str(word.get("text") or "").strip()
            if not word_text:
                continue
            word_start = int(word.get("start") or 0)
            word_end = int(word.get("end") or 0)
            if word_start < clip_end_ms and word_end > clip_start_ms:
                matched_words.append(word_text)

        return " ".join(matched_words).strip()

    def _hydrate_segment_text_from_transcript_cache(
        self,
        video_path: Optional[Path],
        segments: List[Dict[str, Any]],
        *,
        start_time_key: str = "start_time",
        end_time_key: str = "end_time",
        text_key: str = "text",
    ) -> int:
        if video_path is None or not segments:
            return 0

        updated_count = 0
        for segment in segments:
            start_time = str(segment.get(start_time_key) or "").strip()
            end_time = str(segment.get(end_time_key) or "").strip()
            if not start_time or not end_time:
                continue

            try:
                start_seconds = self._parse_timestamp_to_seconds_strict(start_time)
                end_seconds = self._parse_timestamp_to_seconds_strict(end_time)
            except ValueError:
                continue

            if end_seconds <= start_seconds:
                continue

            transcript_window_text = self._extract_text_from_transcript_cache(
                video_path=video_path,
                clip_start=start_seconds,
                clip_end=end_seconds,
            )
            if not transcript_window_text:
                continue

            segment[text_key] = transcript_window_text
            updated_count += 1

        return updated_count

    async def get_user_zai_routing_mode(self, user_id: str) -> str:
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")
        return await self.task_repo.get_user_zai_routing_mode(self.db, user_id)

    async def set_user_zai_routing_mode(self, user_id: str, routing_mode: str) -> str:
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")
        normalized_mode = self._normalize_zai_routing_mode(routing_mode)
        return await self.task_repo.set_user_zai_routing_mode(self.db, user_id, normalized_mode)

    async def save_user_ai_profile_key(
        self,
        user_id: str,
        provider: str,
        profile_name: str,
        api_key: str,
    ) -> None:
        normalized_provider = (provider or "").strip().lower()
        normalized_profile = (profile_name or "").strip().lower()
        if normalized_provider != "zai":
            raise ValueError(f"Unsupported AI provider profile routing: {provider}")
        if normalized_profile not in SUPPORTED_ZAI_KEY_PROFILES:
            raise ValueError(f"Unsupported key profile: {profile_name}")
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")
        encrypted = self.secret_service.encrypt(api_key)
        await self.task_repo.set_user_ai_key_profile(
            self.db,
            user_id,
            normalized_provider,
            normalized_profile,
            encrypted,
        )

    async def clear_user_ai_profile_key(
        self,
        user_id: str,
        provider: str,
        profile_name: str,
    ) -> None:
        normalized_provider = (provider or "").strip().lower()
        normalized_profile = (profile_name or "").strip().lower()
        if normalized_provider != "zai":
            raise ValueError(f"Unsupported AI provider profile routing: {provider}")
        if normalized_profile not in SUPPORTED_ZAI_KEY_PROFILES:
            raise ValueError(f"Unsupported key profile: {profile_name}")
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")
        await self.task_repo.clear_user_ai_key_profile(
            self.db,
            user_id,
            normalized_provider,
            normalized_profile,
        )

    async def get_effective_user_ai_api_key_attempts(
        self,
        user_id: str,
        provider: str,
        zai_routing_mode: Optional[str] = None,
    ) -> Tuple[List[Dict[str, str]], Optional[str]]:
        normalized_provider = (provider or "").strip().lower()
        if normalized_provider not in SUPPORTED_AI_PROVIDERS:
            raise ValueError(f"Unsupported AI provider: {provider}")
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")
        if normalized_provider not in AI_KEY_REQUIRED_PROVIDERS:
            return [], None

        attempts: List[Dict[str, str]] = []
        seen_keys: set[str] = set()

        def append_attempt(label: str, key: Optional[str]) -> None:
            normalized_key = (key or "").strip()
            if not normalized_key:
                return
            if normalized_key in seen_keys:
                return
            seen_keys.add(normalized_key)
            attempts.append({"label": label, "key": normalized_key})

        if normalized_provider != "zai":
            stored_encrypted_ai_key = await self.task_repo.get_user_encrypted_ai_key(
                self.db,
                user_id,
                normalized_provider,
            )
            if stored_encrypted_ai_key:
                append_attempt("saved", self.secret_service.decrypt(stored_encrypted_ai_key))
            append_attempt("env", self._env_ai_key_for_provider(normalized_provider))
            return attempts, None

        if zai_routing_mode is None:
            resolved_mode = await self.task_repo.get_user_zai_routing_mode(self.db, user_id)
        else:
            resolved_mode = self._normalize_zai_routing_mode(zai_routing_mode)

        subscription_key_encrypted = await self.task_repo.get_user_ai_key_profile_encrypted(
            self.db,
            user_id,
            "zai",
            "subscription",
        )
        metered_key_encrypted = await self.task_repo.get_user_ai_key_profile_encrypted(
            self.db,
            user_id,
            "zai",
            "metered",
        )
        legacy_key_encrypted = await self.task_repo.get_user_encrypted_ai_key(
            self.db,
            user_id,
            "zai",
        )
        subscription_key = self.secret_service.decrypt(subscription_key_encrypted) if subscription_key_encrypted else None
        metered_key = self.secret_service.decrypt(metered_key_encrypted) if metered_key_encrypted else None
        legacy_key = self.secret_service.decrypt(legacy_key_encrypted) if legacy_key_encrypted else None
        env_key = self._env_ai_key_for_provider("zai")

        if resolved_mode == "subscription":
            append_attempt("subscription", subscription_key)
        elif resolved_mode == "metered":
            append_attempt("metered", metered_key)
        else:
            append_attempt("subscription", subscription_key)
            append_attempt("metered", metered_key)
            append_attempt("saved", legacy_key)
            append_attempt("env", env_key)

        return attempts, resolved_mode

    def _compute_completion_message(self, result: Dict[str, Any], clip_ids: List[str]) -> str:
        completion_message = "Complete!"
        if len(clip_ids) > 0:
            return completion_message

        analysis_diagnostics = result.get("analysis_diagnostics") or {}
        clip_diagnostics = result.get("clip_generation_diagnostics") or {}
        raw_segments = analysis_diagnostics.get("raw_segments")
        validated_segments = analysis_diagnostics.get("validated_segments")
        error_text = analysis_diagnostics.get("error")

        if error_text:
            return f"No clips generated: AI analysis failed ({error_text})"

        if validated_segments == 0:
            rejected_counts = analysis_diagnostics.get("rejected_counts") or {}
            human_labels = {
                "insufficient_text": "too little text",
                "identical_timestamps": "same start/end timestamp",
                "invalid_duration": "invalid duration",
                "too_short": "segment too short",
                "invalid_timestamp_format": "bad timestamp format",
            }
            reject_bits = []
            for key, label in human_labels.items():
                count = rejected_counts.get(key, 0)
                if count:
                    reject_bits.append(f"{label}: {count}")
            rejection_summary = " ".join(reject_bits) if reject_bits else "no valid segments met timing/quality checks."
            return (
                "No clips generated: transcript did not contain strong standalone moments "
                f"(hooks, value, emotion, complete thought, 10-45s). {rejection_summary}"
            )

        created_clips = clip_diagnostics.get("created_clips", 0)
        attempted_segments = clip_diagnostics.get("attempted_segments", validated_segments or 0)
        sample_failures = clip_diagnostics.get("failure_samples") or []
        if attempted_segments > 0 and created_clips == 0:
            sample_error = sample_failures[0].get("error") if sample_failures else "rendering error"
            return (
                f"No clips generated: AI found {validated_segments} clip-worthy segments, "
                f"but rendering failed for all {attempted_segments}. Example error: {sample_error}"
            )

        return (
            f"No clips generated: AI returned {raw_segments or 0} segments, "
            f"{validated_segments or 0} passed validation, but none were rendered successfully."
        )

    async def _persist_generated_clips(
        self,
        task_id: str,
        clips: List[Dict[str, Any]],
    ) -> List[str]:
        clip_ids: List[str] = []
        for i, clip_info in enumerate(clips):
            clip_id = await self.clip_repo.create_clip(
                self.db,
                task_id=task_id,
                filename=clip_info["filename"],
                file_path=clip_info["path"],
                start_time=clip_info["start_time"],
                end_time=clip_info["end_time"],
                duration=clip_info["duration"],
                text=clip_info.get("text"),
                relevance_score=clip_info.get("relevance_score", 0.0),
                reasoning=clip_info.get("reasoning"),
                clip_order=i + 1,
            )
            clip_ids.append(clip_id)

        await self.task_repo.update_task_clips(self.db, task_id, clip_ids)
        return clip_ids

    async def _resolve_processing_credentials(
        self,
        transcription_provider: str,
        ai_provider: str,
        ai_model: Optional[str],
        ai_routing_mode: Optional[str],
        user_id: Optional[str],
    ) -> Tuple[Optional[str], str, Optional[str], Optional[str], Optional[str], List[str], List[str], Optional[Dict[str, Any]]]:
        assembly_api_key: Optional[str] = None
        if transcription_provider == "assemblyai":
            stored_encrypted_key = None
            if user_id:
                stored_encrypted_key = await self.task_repo.get_user_encrypted_assembly_key(self.db, user_id)
            if stored_encrypted_key:
                assembly_api_key = self.secret_service.decrypt(stored_encrypted_key)
            else:
                assembly_api_key = config.assembly_ai_api_key

        selected_ai_provider = (ai_provider or "openai").strip().lower()
        resolved_zai_routing_mode: Optional[str] = None
        ai_key_attempts: List[Dict[str, str]] = []
        ai_base_url: Optional[str] = None
        ai_request_options: Optional[Dict[str, Any]] = None
        if selected_ai_provider in AI_KEY_REQUIRED_PROVIDERS:
            if user_id:
                ai_key_attempts, resolved_zai_routing_mode = await self.get_effective_user_ai_api_key_attempts(
                    user_id=user_id,
                    provider=selected_ai_provider,
                    zai_routing_mode=ai_routing_mode,
                )
            else:
                fallback_key = self._env_ai_key_for_provider(selected_ai_provider)
                if fallback_key:
                    ai_key_attempts = [{"label": "env", "key": fallback_key}]
        elif selected_ai_provider == "ollama":
            ollama_settings = await self._resolve_effective_ollama_settings(user_id=user_id)
            ai_base_url = str(ollama_settings["base_url"])
            resolved_model = self._resolve_ai_model("ollama", ai_model)
            ai_request_options, _preset = self._build_ollama_request_options(
                profile_name=ollama_settings.get("profile_name"),
                auth_mode=ollama_settings.get("auth_mode"),
                auth_headers=dict(ollama_settings.get("auth_headers") or {}),
                timeout_seconds=int(ollama_settings["timeout_seconds"]),
                max_retries=int(ollama_settings["max_retries"]),
                retry_backoff_ms=int(ollama_settings["retry_backoff_ms"]),
                model_name=resolved_model,
            )

        ai_api_key = ai_key_attempts[0]["key"] if ai_key_attempts else None
        ai_api_key_fallbacks = [attempt["key"] for attempt in ai_key_attempts[1:]]
        ai_key_labels = [attempt["label"] for attempt in ai_key_attempts]

        return (
            assembly_api_key,
            selected_ai_provider,
            resolved_zai_routing_mode,
            ai_api_key,
            ai_base_url,
            ai_api_key_fallbacks,
            ai_key_labels,
            ai_request_options,
        )

    async def _process_review_enabled_analysis(
        self,
        task_id: str,
        url: str,
        source_type: str,
        source_options: Optional[Dict[str, Any]],
        transcription_provider: str,
        ai_provider: str,
        ai_model: Optional[str],
        ai_routing_mode: Optional[str],
        transcription_options: Optional[Dict[str, Any]],
        ai_focus_tags: Optional[List[str]],
        subtitle_style: Optional[Dict[str, Any]],
        progress_callback: Optional[Callable],
        cancel_check: Optional[Callable[[], Awaitable[None]]],
        user_id: Optional[str],
        update_progress: Callable[[int, str, Optional[Dict[str, Any]]], Awaitable[None]],
        task_video_overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        user_video_preferences = await self._get_effective_user_video_preferences(
            user_id,
            task_video_overrides=task_video_overrides,
        )

        (
            assembly_api_key,
            selected_ai_provider,
            resolved_zai_routing_mode,
            ai_api_key,
            ai_base_url,
            ai_api_key_fallbacks,
            ai_key_labels,
            ai_request_options,
        ) = await self._resolve_processing_credentials(
            transcription_provider=transcription_provider,
            ai_provider=ai_provider,
            ai_model=ai_model,
            ai_routing_mode=ai_routing_mode,
            user_id=user_id,
        )

        analysis_result = await self.video_service.process_video_analysis(
            url=url,
            source_type=source_type,
            source_options=source_options,
            transcription_provider=transcription_provider,
            assembly_api_key=assembly_api_key,
            ai_provider=selected_ai_provider,
            ai_api_key=ai_api_key,
            ai_base_url=ai_base_url,
            ai_api_key_fallbacks=ai_api_key_fallbacks,
            ai_key_labels=ai_key_labels,
            ai_routing_mode=resolved_zai_routing_mode,
            ai_model=ai_model,
            ai_request_options=ai_request_options,
            transcription_options=transcription_options,
            ai_focus_tags=ai_focus_tags,
            default_framing_mode=str(user_video_preferences.get("effective_default_framing_mode") or "auto"),
            face_detection_mode=str(user_video_preferences.get("default_face_detection_mode") or "balanced"),
            fallback_crop_position=str(user_video_preferences.get("default_fallback_crop_position") or "center"),
            face_anchor_profile=str(user_video_preferences.get("default_face_anchor_profile") or "auto"),
            progress_callback=update_progress,
            cancel_check=cancel_check,
        )
        analysis_video_path = Path(str(analysis_result.get("video_path") or "")) if analysis_result.get("video_path") else None
        review_auto_select_min_score = self._resolve_review_auto_select_min_score(
            await self.task_repo.get_task_by_id(self.db, task_id)
        )

        await self.task_repo.update_task_status(
            self.db,
            task_id,
            "processing",
            progress=95,
            progress_message="Saving draft clips...",
        )

        drafts_payload: List[Dict[str, Any]] = []
        for index, segment in enumerate(analysis_result.get("segments") or [], start=1):
            start_time = str(segment.get("start_time") or "00:00")
            end_time = str(segment.get("end_time") or "00:00")
            try:
                start_seconds, end_seconds, duration_seconds = self._validate_clip_window(start_time, end_time)
            except ValueError as validation_error:
                logger.warning(
                    "Skipping invalid draft segment for task %s (%s -> %s): %s",
                    task_id,
                    start_time,
                    end_time,
                    validation_error,
                )
                continue

            transcript_text = self._extract_text_from_transcript_cache(
                analysis_video_path,
                start_seconds,
                end_seconds,
            ) if analysis_video_path is not None else ""
            text_value = transcript_text or str(segment.get("text") or "").strip()
            framing_metadata = (
                dict(segment.get("framing_metadata"))
                if isinstance(segment.get("framing_metadata"), dict)
                else {}
            )
            review_score = float(
                segment.get("review_score")
                if segment.get("review_score") is not None
                else segment.get("relevance_score") or 0.0
            )
            is_selected = self._should_auto_select_review_draft(
                review_score=review_score,
                framing_metadata=framing_metadata,
                min_review_score=review_auto_select_min_score,
            )
            drafts_payload.append(
                {
                    "clip_order": index,
                    "start_time": self._format_seconds_to_timestamp(start_seconds),
                    "end_time": self._format_seconds_to_timestamp(end_seconds),
                    "duration": duration_seconds,
                    "original_start_time": self._format_seconds_to_timestamp(start_seconds),
                    "original_end_time": self._format_seconds_to_timestamp(end_seconds),
                    "original_duration": duration_seconds,
                    "original_text": text_value,
                    "edited_text": text_value,
                    "relevance_score": float(segment.get("relevance_score") or 0.0),
                    "review_score": review_score,
                    "framing_metadata_json": framing_metadata,
                    "framing_mode_override": self._normalize_framing_mode_override(
                        segment.get("framing_mode_override")
                        or user_video_preferences.get("effective_default_framing_mode")
                    ),
                    "reasoning": segment.get("reasoning"),
                    "created_by_user": False,
                    "is_selected": is_selected,
                    "auto_selection_rule_excluded": review_auto_select_min_score is not None and not is_selected,
                    "is_deleted": False,
                    "edited_word_timings_json": None,
                }
            )
            drafts_payload[-1].update(self._build_draft_feedback_state(drafts_payload[-1]))

        created_draft_ids = await self.draft_clip_repo.replace_task_drafts(self.db, task_id, drafts_payload)
        for draft, draft_id in zip(drafts_payload, created_draft_ids):
            draft["id"] = draft_id
        if analysis_video_path is not None:
            await self._persist_draft_preview_strips(
                task_id,
                drafts_payload,
                video_path=analysis_video_path,
                reset_existing=True,
            )
        await self.task_repo.update_task_status(
            self.db,
            task_id,
            "awaiting_review",
            progress=100,
            progress_message="Analysis complete. Review draft clips before rendering.",
        )

        return {
            "task_id": task_id,
            "drafts_count": len(drafts_payload),
            "segments": analysis_result.get("segments") or [],
            "summary": analysis_result.get("summary"),
            "key_topics": analysis_result.get("key_topics"),
            "final_status": "awaiting_review",
            "final_progress": 100,
            "final_message": "Analysis complete. Awaiting review.",
        }

    async def _process_non_review_pipeline(
        self,
        task_id: str,
        url: str,
        source_type: str,
        source_options: Optional[Dict[str, Any]],
        font_family: str,
        font_size: int,
        font_color: str,
        transitions_enabled: bool,
        transcription_provider: str,
        ai_provider: str,
        ai_model: Optional[str],
        ai_routing_mode: Optional[str],
        transcription_options: Optional[Dict[str, Any]],
        ai_focus_tags: Optional[List[str]],
        subtitle_style: Optional[Dict[str, Any]],
        progress_callback: Optional[Callable],
        cancel_check: Optional[Callable[[], Awaitable[None]]],
        user_id: Optional[str],
        update_progress: Callable[[int, str, Optional[Dict[str, Any]]], Awaitable[None]],
        render_filename_prefix: Optional[str] = None,
        task_video_overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        user_video_preferences = await self._get_effective_user_video_preferences(
            user_id,
            task_video_overrides=task_video_overrides,
        )

        (
            assembly_api_key,
            selected_ai_provider,
            resolved_zai_routing_mode,
            ai_api_key,
            ai_base_url,
            ai_api_key_fallbacks,
            ai_key_labels,
            ai_request_options,
        ) = await self._resolve_processing_credentials(
            transcription_provider=transcription_provider,
            ai_provider=ai_provider,
            ai_model=ai_model,
            ai_routing_mode=ai_routing_mode,
            user_id=user_id,
        )

        result = await self.video_service.process_video_complete(
            url=url,
            source_type=source_type,
            source_options=source_options,
            font_family=font_family,
            font_size=font_size,
            font_color=font_color,
            transitions_enabled=transitions_enabled,
            transcription_provider=transcription_provider,
            assembly_api_key=assembly_api_key,
            ai_provider=selected_ai_provider,
            ai_api_key=ai_api_key,
            ai_base_url=ai_base_url,
            ai_api_key_fallbacks=ai_api_key_fallbacks,
            ai_key_labels=ai_key_labels,
            ai_routing_mode=resolved_zai_routing_mode,
            ai_model=ai_model,
            ai_request_options=ai_request_options,
            transcription_options=transcription_options,
            ai_focus_tags=ai_focus_tags,
            subtitle_style=subtitle_style,
            default_framing_mode=str(user_video_preferences.get("effective_default_framing_mode") or "auto"),
            face_detection_mode=str(user_video_preferences.get("default_face_detection_mode") or "balanced"),
            fallback_crop_position=str(user_video_preferences.get("default_fallback_crop_position") or "center"),
            face_anchor_profile=str(user_video_preferences.get("default_face_anchor_profile") or "auto"),
            progress_callback=update_progress,
            cancel_check=cancel_check,
            filename_prefix=render_filename_prefix,
        )
        result_video_path = Path(str(result.get("video_path") or "")) if result.get("video_path") else None
        if result_video_path is not None:
            aligned_count = self._hydrate_segment_text_from_transcript_cache(
                result_video_path,
                result.get("clips") or [],
                start_time_key="start_time",
                end_time_key="end_time",
                text_key="text",
            )
            if aligned_count:
                logger.info(
                    "Aligned clip text from transcript cache for task %s (%s clips)",
                    task_id,
                    aligned_count,
                )

        await self.task_repo.update_task_status(
            self.db,
            task_id,
            "processing",
            progress=95,
            progress_message="Saving clips...",
        )

        await self.draft_clip_repo.delete_drafts_by_task(self.db, task_id)
        clip_ids = await self._persist_generated_clips(task_id, result.get("clips") or [])

        completion_message = self._compute_completion_message(result, clip_ids)
        await self.task_repo.update_task_status(
            self.db,
            task_id,
            "completed",
            progress=100,
            progress_message=completion_message,
        )

        logger.info(f"Task {task_id} completed successfully with {len(clip_ids)} clips")

        return {
            "task_id": task_id,
            "clips_count": len(clip_ids),
            "segments": result.get("segments") or [],
            "summary": result.get("summary"),
            "key_topics": result.get("key_topics"),
            "final_status": "completed",
            "final_progress": 100,
            "final_message": completion_message,
        }

    async def _render_from_drafts(
        self,
        task_id: str,
        url: str,
        source_type: str,
        user_id: Optional[str],
        font_family: str,
        font_size: int,
        font_color: str,
        transitions_enabled: bool,
        subtitle_style: Optional[Dict[str, Any]],
        cancel_check: Optional[Callable[[], Awaitable[None]]],
        update_progress: Callable[[int, str, Optional[Dict[str, Any]]], Awaitable[None]],
    ) -> Dict[str, Any]:
        await update_progress(10, "Loading approved draft clips...")

        render_filename_prefix = self._build_render_filename_prefix()
        drafts = await self.draft_clip_repo.get_drafts_by_task(self.db, task_id)
        selected_drafts = [draft for draft in drafts if draft.get("is_selected") and not draft.get("is_deleted")]
        if not selected_drafts:
            raise ValueError("Finalize requires at least one selected draft clip")
        self._validate_non_overlapping_draft_windows(selected_drafts)

        selected_drafts.sort(
            key=lambda draft: (
                self._parse_timestamp_to_seconds_strict(str(draft.get("start_time") or "00:00")),
                int(draft.get("clip_order") or 0),
            )
        )

        await update_progress(15, "Preparing source media...")
        video_path = await self.resolve_video_path_for_user(
            url=url,
            source_type=source_type,
            user_id=user_id,
        )

        rendered_segments: List[Dict[str, Any]] = []
        total_selected = len(selected_drafts)
        for index, draft in enumerate(selected_drafts, start=1):
            start_time = str(draft.get("start_time") or "").strip()
            end_time = str(draft.get("end_time") or "").strip()
            start_seconds, end_seconds, duration_seconds = self._validate_clip_window(start_time, end_time)

            original_text = str(draft.get("original_text") or "").strip()
            edited_text = str(draft.get("edited_text") or "").strip() or original_text
            if not edited_text:
                raise ValueError(f"Selected clip {draft.get('clip_order')} has empty subtitle text")

            text_was_edited = self._normalize_text_for_compare(edited_text) != self._normalize_text_for_compare(original_text)
            word_timings_override = None
            if text_was_edited:
                await update_progress(
                    20,
                    f"Aligning edited subtitles ({index}/{total_selected})...",
                    {
                        "stage": "analysis",
                        "stage_progress": int((index / total_selected) * 100),
                        "overall_progress": 20,
                    },
                )
                try:
                    word_timings_override = await self.video_service.align_edited_subtitle_words(
                        video_path=video_path,
                        clip_start=start_seconds,
                        clip_end=end_seconds,
                        edited_text=edited_text,
                    )
                except Exception as alignment_error:
                    raise ValueError(
                        f"Failed to align edited subtitles for clip {draft.get('clip_order')}: {alignment_error}"
                    ) from alignment_error

                await self.draft_clip_repo.update_draft_word_timings(
                    self.db,
                    task_id=task_id,
                    draft_id=str(draft["id"]),
                    word_timings=word_timings_override,
                )
            else:
                if draft.get("edited_word_timings_json") is not None:
                    await self.draft_clip_repo.update_draft_word_timings(
                        self.db,
                        task_id=task_id,
                        draft_id=str(draft["id"]),
                        word_timings=None,
                    )

            rendered_segments.append(
                {
                    "start_time": self._format_seconds_to_timestamp(start_seconds),
                    "end_time": self._format_seconds_to_timestamp(end_seconds),
                    "duration": duration_seconds,
                    "text": edited_text,
                    "relevance_score": float(
                        draft.get("review_score")
                        if draft.get("review_score") is not None
                        else draft.get("relevance_score") or 0.0
                    ),
                    "framing_metadata": (
                        dict(draft.get("framing_metadata_json"))
                        if isinstance(draft.get("framing_metadata_json"), dict)
                        else {}
                    ),
                    "framing_mode_override": self._normalize_framing_mode_override(
                        draft.get("framing_mode_override")
                    ),
                    "reasoning": draft.get("reasoning"),
                    "subtitle_word_timings": word_timings_override,
                }
            )

        await update_progress(65, "Rendering approved clips...")
        render_result = await self.video_service.render_video_segments(
            video_path=video_path,
            segments=rendered_segments,
            font_family=font_family,
            font_size=font_size,
            font_color=font_color,
            subtitle_style=subtitle_style,
            transitions_enabled=transitions_enabled,
            progress_callback=update_progress,
            cancel_check=cancel_check,
            filename_prefix=render_filename_prefix,
        )

        await self.task_repo.update_task_status(
            self.db,
            task_id,
            "processing",
            progress=95,
            progress_message="Saving clips...",
        )

        await self.clip_repo.delete_clips_by_task(self.db, task_id)
        clip_ids = await self._persist_generated_clips(task_id, render_result.get("clips") or [])

        completion_message = "Complete!" if clip_ids else "No clips were rendered from selected draft clips."
        await self.task_repo.update_task_status(
            self.db,
            task_id,
            "completed",
            progress=100,
            progress_message=completion_message,
        )

        return {
            "task_id": task_id,
            "clips_count": len(clip_ids),
            "segments": rendered_segments,
            "summary": None,
            "key_topics": None,
            "final_status": "completed",
            "final_progress": 100,
            "final_message": completion_message,
        }

    async def process_task(
        self,
        task_id: str,
        url: str,
        source_type: str,
        source_options: Optional[Dict[str, Any]] = None,
        font_family: str = "TikTokSans-Regular",
        font_size: int = 24,
        font_color: str = "#FFFFFF",
        transitions_enabled: bool = False,
        transcription_provider: str = "local",
        ai_provider: str = "openai",
        ai_model: Optional[str] = None,
        ai_routing_mode: Optional[str] = None,
        transcription_options: Optional[Dict[str, Any]] = None,
        subtitle_style: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable] = None,
        cancel_check: Optional[Callable[[], Awaitable[None]]] = None,
        user_id: Optional[str] = None,
        render_from_drafts: bool = False,
    ) -> Dict[str, Any]:
        """
        Process a task.
        - default path: full one-pass processing (or analysis-only when review is enabled)
        - finalize path: render clips from reviewed drafts
        """
        try:
            logger.info(f"Starting processing for task {task_id} (render_from_drafts={render_from_drafts})")

            task_record = await self.task_repo.get_task_by_id(self.db, task_id)
            review_before_render_enabled = bool((task_record or {}).get("review_before_render_enabled", True))
            has_drafts = bool(render_from_drafts)
            has_generated_clips = False
            processing_started_at_ms = self._runtime_time_ms()
            current_runtime_info = self._merge_runtime_info(
                (task_record or {}).get("runtime_info") if isinstance((task_record or {}).get("runtime_info"), dict) else {},
                {
                    "runtime_scope": "task",
                    "render_from_drafts": bool(render_from_drafts),
                    "current_stage": "setup",
                    **self._open_processing_runtime_window(
                        (task_record or {}).get("runtime_info") if isinstance((task_record or {}).get("runtime_info"), dict) else {},
                        started_at_ms=processing_started_at_ms,
                        render_from_drafts=bool(render_from_drafts),
                    ),
                },
            )
            current_checkpoint = "started"

            async def persist_task_status(
                status: str,
                *,
                progress: Optional[int] = None,
                message: Optional[str] = None,
                metadata: Optional[Dict[str, Any]] = None,
                checkpoint: Optional[str] = None,
                clear_failure: bool = False,
                failure_code: Optional[str] = None,
                failure_hint: Optional[str] = None,
            ) -> None:
                nonlocal current_runtime_info, current_checkpoint, has_drafts, has_generated_clips
                normalized_metadata = dict(metadata or {})
                inferred_checkpoint = checkpoint
                stage_name = str(normalized_metadata.get("stage") or current_runtime_info.get("current_stage") or "setup")
                if inferred_checkpoint is None:
                    if status == "completed":
                        inferred_checkpoint = "completed"
                    elif status == "awaiting_review":
                        inferred_checkpoint = "analyzed"
                    elif status == "error":
                        inferred_checkpoint = "failed"
                    elif stage_name == "download" and int(normalized_metadata.get("stage_progress") or 0) >= 100:
                        inferred_checkpoint = "downloaded"
                    elif stage_name == "transcript" and int(normalized_metadata.get("stage_progress") or 0) >= 100:
                        inferred_checkpoint = "transcribed"
                    elif stage_name == "analysis" and int(normalized_metadata.get("stage_progress") or 0) >= 100:
                        inferred_checkpoint = "analyzed"
                    elif stage_name == "clips" and normalized_metadata.get("clip_started"):
                        inferred_checkpoint = "review_approved" if review_before_render_enabled or render_from_drafts else "analyzed"
                    else:
                        inferred_checkpoint = current_checkpoint

                current_checkpoint = self._normalize_stage_checkpoint(inferred_checkpoint)
                runtime_timing_update: Dict[str, Any] = {}
                if status in {"awaiting_review", "completed", "error"}:
                    runtime_timing_update = self._close_processing_runtime_window(
                        current_runtime_info,
                        ended_at_ms=self._runtime_time_ms(),
                        final_status=status,
                        render_from_drafts=bool(render_from_drafts),
                    )
                current_runtime_info = self._merge_runtime_info(
                    current_runtime_info,
                    {
                        "status": status,
                        "latest_message": message,
                        "current_stage": stage_name,
                        "latest_stage_metadata": normalized_metadata,
                        "stage_label": normalized_metadata.get("stage_label"),
                        **runtime_timing_update,
                    },
                )
                await self.task_repo.update_task_status(
                    self.db,
                    task_id,
                    status,
                    progress=progress,
                    progress_message=message,
                    runtime_info=current_runtime_info,
                    failure_code=failure_code,
                    failure_hint=failure_hint,
                    stage_checkpoint=current_checkpoint,
                    retryable_from_stages=self._compute_retryable_stages(
                        current_checkpoint,
                        review_before_render_enabled=review_before_render_enabled,
                        has_drafts=has_drafts,
                        has_generated_clips=has_generated_clips,
                    ),
                    clear_failure=clear_failure,
                )

            await persist_task_status(
                "processing",
                progress=0,
                message="Starting...",
                metadata={"stage": "setup", "stage_progress": 0, "overall_progress": 0},
                checkpoint="started",
                clear_failure=True,
            )
            if cancel_check:
                await cancel_check()

            progress_lock = asyncio.Lock()

            async def update_progress(
                progress: int,
                message: str,
                metadata: Optional[Dict[str, Any]] = None,
            ) -> None:
                async with progress_lock:
                    if cancel_check:
                        await cancel_check()
                    await persist_task_status(
                        "processing",
                        progress=progress,
                        message=message,
                        metadata=metadata,
                        clear_failure=True,
                    )
                    if progress_callback:
                        await progress_callback(progress, message, metadata)
                    if cancel_check:
                        await cancel_check()

            if render_from_drafts:
                return await self._render_from_drafts(
                    task_id=task_id,
                    url=url,
                    source_type=source_type,
                    user_id=user_id,
                    font_family=font_family,
                    font_size=font_size,
                    font_color=font_color,
                    transitions_enabled=transitions_enabled,
                    subtitle_style=subtitle_style,
                    cancel_check=cancel_check,
                    update_progress=update_progress,
                )

            ai_focus_tags = list((task_record or {}).get("ai_focus_tags") or [])
            render_filename_prefix = self._build_render_filename_prefix()
            task_video_overrides = (
                dict((task_record or {}).get("runtime_info", {}).get("video_preferences_override"))
                if isinstance((task_record or {}).get("runtime_info", {}).get("video_preferences_override"), dict)
                else None
            )

            if review_before_render_enabled:
                result = await self._process_review_enabled_analysis(
                    task_id=task_id,
                    url=url,
                    source_type=source_type,
                    source_options=source_options,
                    transcription_provider=transcription_provider,
                    ai_provider=ai_provider,
                    ai_model=ai_model,
                    ai_routing_mode=ai_routing_mode,
                    transcription_options=transcription_options,
                    ai_focus_tags=ai_focus_tags,
                    subtitle_style=subtitle_style,
                    progress_callback=progress_callback,
                    cancel_check=cancel_check,
                    user_id=user_id,
                    update_progress=update_progress,
                    task_video_overrides=task_video_overrides,
                )
                has_drafts = bool(int(result.get("drafts_count") or 0) > 0)
                await persist_task_status(
                    "awaiting_review",
                    progress=int(result.get("final_progress") or 100),
                    message=str(result.get("final_message") or "Analysis complete. Awaiting review."),
                    metadata={"stage": "analysis", "stage_progress": 100, "overall_progress": int(result.get("final_progress") or 100)},
                    checkpoint="analyzed",
                    clear_failure=True,
                )
                return result

            result = await self._process_non_review_pipeline(
                task_id=task_id,
                url=url,
                source_type=source_type,
                source_options=source_options,
                font_family=font_family,
                font_size=font_size,
                font_color=font_color,
                transitions_enabled=transitions_enabled,
                transcription_provider=transcription_provider,
                ai_provider=ai_provider,
                ai_model=ai_model,
                ai_routing_mode=ai_routing_mode,
                transcription_options=transcription_options,
                ai_focus_tags=ai_focus_tags,
                subtitle_style=subtitle_style,
                progress_callback=progress_callback,
                cancel_check=cancel_check,
                user_id=user_id,
                update_progress=update_progress,
                render_filename_prefix=render_filename_prefix,
                task_video_overrides=task_video_overrides,
            )
            has_generated_clips = bool(int(result.get("clips_count") or 0) > 0)
            await persist_task_status(
                "completed",
                progress=int(result.get("final_progress") or 100),
                message=str(result.get("final_message") or "Complete!"),
                metadata={"stage": "finalizing", "stage_progress": 100, "overall_progress": int(result.get("final_progress") or 100)},
                checkpoint="completed",
                clear_failure=True,
            )
            return result

        except Exception as e:
            logger.error(f"Error processing task {task_id}: {e}")
            failure_code, failure_hint = self._classify_failure(e)
            failure_runtime_info = current_runtime_info if "current_runtime_info" in locals() else None
            if isinstance(failure_runtime_info, dict):
                failure_runtime_info = self._merge_runtime_info(
                    failure_runtime_info,
                    self._close_processing_runtime_window(
                        failure_runtime_info,
                        ended_at_ms=self._runtime_time_ms(),
                        final_status="error",
                        render_from_drafts=bool(render_from_drafts),
                    ),
                )
            await self.task_repo.update_task_status(
                self.db,
                task_id,
                "error",
                progress_message=str(e),
                runtime_info=failure_runtime_info,
                failure_code=failure_code,
                failure_hint=failure_hint,
                stage_checkpoint="failed",
                retryable_from_stages=self._compute_retryable_stages(
                    self._normalize_stage_checkpoint(
                        current_checkpoint if "current_checkpoint" in locals() else "queued"
                    ),
                    review_before_render_enabled=review_before_render_enabled if "review_before_render_enabled" in locals() else True,
                    has_drafts=has_drafts if "has_drafts" in locals() else False,
                    has_generated_clips=has_generated_clips if "has_generated_clips" in locals() else False,
                ),
            )
            raise

    async def get_task_draft_clips(self, task_id: str) -> List[Dict[str, Any]]:
        task = await self.task_repo.get_task_by_id(self.db, task_id)
        drafts = await self.draft_clip_repo.get_drafts_by_task(self.db, task_id)
        if not task:
            return drafts
        return self._attach_draft_view_fields(task_id, drafts)

    async def get_runtime_overview(self) -> Dict[str, Any]:
        from ..whisper_runtime import get_local_whisper_model_metadata
        from ..workers.job_queue import JobQueue

        pool = await JobQueue.get_pool()
        queue_names = [
            config.arq_local_queue_name,
            config.arq_local_gpu_queue_name,
            config.arq_assembly_queue_name,
        ]
        queue_stats: List[Dict[str, Any]] = []
        for queue_name in queue_names:
            queue_depth = int(await pool.zcard(queue_name))
            queue_stats.append({"queue_name": queue_name, "depth": queue_depth})

        worker_heartbeats = await self._read_worker_heartbeats(pool)

        retention_policy = {
            "downloads_max_age_hours": 24,
            "transcript_cache_max_age_hours": 72,
            "waveform_cache_max_age_hours": 72,
            "draft_preview_storage": "task_artifacts",
            "legacy_temp_draft_preview_max_age_hours": 72,
            "failed_task_artifacts_max_age_hours": 168,
        }

        return {
            "workers": worker_heartbeats,
            "queues": queue_stats,
            "local_whisper_runtime": self._select_worker_runtime_from_heartbeats(worker_heartbeats),
            "local_whisper_models": get_local_whisper_model_metadata(),
            "recent_failures": await self.task_repo.get_recent_failed_tasks(self.db, limit=8),
            "failure_summary": await self.task_repo.get_failure_summary(self.db, limit=8),
            "retention_policy": retention_policy,
        }

    async def retry_task_from_stage(self, task_id: str, retry_from_stage: Optional[str]) -> Dict[str, Any]:
        task = await self.task_repo.get_task_by_id(self.db, task_id)
        if not task:
            raise ValueError("Task not found")

        requested_stage = self._normalize_stage_checkpoint(retry_from_stage or task.get("stage_checkpoint"))
        allowed_stages = list(task.get("retryable_from_stages") or [])
        if requested_stage == "review_approved":
            requested_stage_key = "review_approved"
        else:
            requested_stage_key = requested_stage
        if requested_stage_key not in allowed_stages:
            raise ValueError(f"Task cannot be retried from stage '{requested_stage_key}'")

        source_url = str(task.get("source_url") or "").strip()
        source_type = str(task.get("source_type") or "").strip()
        if not source_url or not source_type:
            raise ValueError("Task source is missing")

        render_from_drafts = requested_stage_key == "review_approved"
        if requested_stage_key == "analyzed" and bool(task.get("review_before_render_enabled")):
            draft_count = len(await self.draft_clip_repo.get_drafts_by_task(self.db, task_id))
            if draft_count > 0:
                await self.task_repo.update_task_status(
                    self.db,
                    task_id,
                    "awaiting_review",
                    progress=100,
                    progress_message="Draft clips restored for review.",
                    clear_failure=True,
                    stage_checkpoint="analyzed",
                    retryable_from_stages=self._compute_retryable_stages(
                        "analyzed",
                        review_before_render_enabled=True,
                        has_drafts=True,
                        has_generated_clips=bool((task.get("clips_count") or 0) > 0),
                    ),
                )
                return {
                    "task_id": task_id,
                    "status": "awaiting_review",
                    "retry_from_stage": requested_stage_key,
                    "message": "Draft clips restored. Review and finalize when ready.",
                }

        await self.task_repo.update_task_status(
            self.db,
            task_id,
            "queued",
            progress=0,
            progress_message=f"Queued retry from {requested_stage_key.replace('_', ' ')}...",
            clear_failure=True,
            stage_checkpoint=requested_stage_key,
            retryable_from_stages=allowed_stages,
        )
        return {
            "task_id": task_id,
            "status": "queued",
            "retry_from_stage": requested_stage_key,
            "render_from_drafts": render_from_drafts,
            "task": task,
        }

    async def update_task_draft_clips(
        self,
        task_id: str,
        updates: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not isinstance(updates, list) or not updates:
            raise ValueError("draft_clips must be a non-empty list")

        existing_by_id = await self.draft_clip_repo.get_draft_map_by_task(self.db, task_id)
        if not existing_by_id:
            raise ValueError("No draft clips found for task")

        normalized_updates: List[Dict[str, Any]] = []
        preview_refresh_ids: List[str] = []
        seen_ids: set[str] = set()
        draft_state: Dict[str, Dict[str, Any]] = {
            draft_id: dict(existing)
            for draft_id, existing in existing_by_id.items()
        }

        for item in updates:
            if not isinstance(item, dict):
                raise ValueError("Each draft clip update must be an object")

            draft_id = str(item.get("id") or "").strip()
            if not draft_id:
                raise ValueError("Each draft clip update must include id")
            if draft_id in seen_ids:
                raise ValueError(f"Duplicate draft clip id in payload: {draft_id}")
            seen_ids.add(draft_id)

            existing = existing_by_id.get(draft_id)
            if not existing:
                raise ValueError(f"Draft clip not found: {draft_id}")

            start_time = str(item.get("start_time", existing["start_time"])).strip()
            end_time = str(item.get("end_time", existing["end_time"])).strip()
            start_seconds, end_seconds, duration_seconds = self._validate_clip_window(start_time, end_time)

            normalized_update: Dict[str, Any] = {
                "id": draft_id,
                "start_time": self._format_seconds_to_timestamp(start_seconds),
                "end_time": self._format_seconds_to_timestamp(end_seconds),
                "duration": duration_seconds,
            }

            if "edited_text" in item:
                if item.get("edited_text") is None:
                    normalized_update["edited_text"] = ""
                else:
                    normalized_update["edited_text"] = str(item.get("edited_text"))

            if "is_selected" in item:
                normalized_update["is_selected"] = bool(item.get("is_selected"))
                normalized_update["selection_changed_by_user"] = True
            if "framing_mode_override" in item:
                normalized_update["framing_mode_override"] = self._normalize_framing_mode_override(
                    item.get("framing_mode_override")
                )

            text_changed = (
                "edited_text" in normalized_update
                and self._normalize_text_for_compare(normalized_update["edited_text"])
                != self._normalize_text_for_compare(existing.get("edited_text"))
            )
            timing_changed = (
                normalized_update["start_time"] != str(existing.get("start_time"))
                or normalized_update["end_time"] != str(existing.get("end_time"))
            )
            if text_changed or timing_changed:
                normalized_update["edited_word_timings_json"] = None
            if timing_changed:
                preview_refresh_ids.append(draft_id)

            draft_state[draft_id].update(normalized_update)
            normalized_update.update(self._build_draft_feedback_state(draft_state[draft_id]))
            normalized_updates.append(normalized_update)

        self._validate_non_overlapping_draft_windows(list(draft_state.values()))

        await self.draft_clip_repo.bulk_update_drafts(self.db, task_id, normalized_updates)
        updated_drafts = await self.draft_clip_repo.get_drafts_by_task(self.db, task_id)
        await self._refresh_draft_preview_strips(task_id, preview_refresh_ids)
        return self._attach_draft_view_fields(task_id, updated_drafts)

    async def create_task_draft_clip(
        self,
        task_id: str,
        start_time: str,
        end_time: str,
        source_url: str,
        source_type: str,
        user_id: Optional[str] = None,
        edited_text: Optional[str] = None,
        is_selected: Optional[bool] = None,
        framing_mode_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        start_seconds, end_seconds, duration_seconds = self._validate_clip_window(start_time, end_time)
        normalized_start_time = self._format_seconds_to_timestamp(start_seconds)
        normalized_end_time = self._format_seconds_to_timestamp(end_seconds)

        existing_drafts = await self.draft_clip_repo.get_drafts_by_task(self.db, task_id)
        proposed_drafts = list(existing_drafts) + [
            {
                "id": "__new__",
                "start_time": normalized_start_time,
                "end_time": normalized_end_time,
                "is_deleted": False,
            }
        ]
        self._validate_non_overlapping_draft_windows(proposed_drafts)

        task_record = await self.task_repo.get_task_by_id(self.db, task_id)
        task_video_overrides = (
            dict((task_record or {}).get("runtime_info", {}).get("video_preferences_override"))
            if isinstance((task_record or {}).get("runtime_info", {}).get("video_preferences_override"), dict)
            else None
        )
        user_video_preferences = await self._get_effective_user_video_preferences(
            user_id,
            task_video_overrides=task_video_overrides,
        )
        source_video_path = await self.resolve_video_path_for_user(
            url=source_url,
            source_type=source_type,
            user_id=user_id,
        )
        transcript_text = self._extract_text_from_transcript_cache(
            source_video_path,
            start_seconds,
            end_seconds,
        )
        framing_metadata = await self.video_service.analyze_single_segment_framing(
            video_path=source_video_path,
            start_time=normalized_start_time,
            end_time=normalized_end_time,
            face_detection_mode=str(user_video_preferences.get("default_face_detection_mode") or "balanced"),
            fallback_crop_position=str(user_video_preferences.get("default_fallback_crop_position") or "center"),
            face_anchor_profile=str(user_video_preferences.get("default_face_anchor_profile") or "auto"),
        )

        preferred_text = str(edited_text or "").strip()
        base_text = preferred_text or transcript_text
        clip_order = await self.draft_clip_repo.get_next_clip_order(self.db, task_id)

        payload = {
            "clip_order": clip_order,
            "start_time": normalized_start_time,
            "end_time": normalized_end_time,
            "duration": duration_seconds,
            "original_start_time": normalized_start_time,
            "original_end_time": normalized_end_time,
            "original_duration": duration_seconds,
            "original_text": base_text,
            "edited_text": preferred_text or base_text,
            "relevance_score": 0.0,
            "framing_metadata_json": framing_metadata,
            "framing_mode_override": (
                self._normalize_framing_mode_override(framing_mode_override)
                if framing_mode_override is not None
                else str(user_video_preferences.get("effective_default_framing_mode") or "auto")
            ),
            "reasoning": "Added manually during review",
            "created_by_user": True,
            "is_selected": bool(is_selected) if is_selected is not None else bool(base_text),
            "is_deleted": False,
            "edited_word_timings_json": None,
        }
        payload.update(self._build_draft_feedback_state(payload))
        created_id = await self.draft_clip_repo.create_draft(self.db, task_id, payload)

        draft_map = await self.draft_clip_repo.get_draft_map_by_task(self.db, task_id)
        draft = draft_map.get(created_id)
        if not draft:
            raise ValueError("Failed to create draft clip")
        await self._persist_draft_preview_strips(task_id, [draft], video_path=source_video_path)
        return self._attach_draft_view_fields(task_id, [draft])[0]

    async def delete_task_draft_clip(self, task_id: str, draft_id: str) -> None:
        existing = await self.draft_clip_repo.get_draft_map_by_task(self.db, task_id)
        draft = existing.get(draft_id)
        if not draft:
            raise ValueError("Draft clip not found")
        deleted_draft = dict(draft)
        deleted_draft["is_selected"] = False
        deleted_draft["is_deleted"] = True
        await self.draft_clip_repo.bulk_update_drafts(
            self.db,
            task_id,
            [
                {
                    "id": draft_id,
                    "is_selected": False,
                    "is_deleted": True,
                    **self._build_draft_feedback_state(deleted_draft),
                }
            ],
        )

    async def restore_task_draft_clips(self, task_id: str) -> List[Dict[str, Any]]:
        await self.draft_clip_repo.restore_task_drafts(self.db, task_id)
        restored_all = await self.draft_clip_repo.get_drafts_by_task(self.db, task_id, include_deleted=True)
        feedback_updates = [
            {
                "id": str(draft["id"]),
                **self._build_draft_feedback_state(draft),
            }
            for draft in restored_all
        ]
        if feedback_updates:
            await self.draft_clip_repo.bulk_update_drafts(
                self.db,
                task_id,
                feedback_updates,
                include_deleted=True,
            )
        restored = await self.draft_clip_repo.get_drafts_by_task(self.db, task_id)
        self._validate_non_overlapping_draft_windows(restored)
        return self._attach_draft_view_fields(task_id, restored)

    async def get_user_transcription_settings(self, user_id: str) -> Dict[str, Any]:
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")
        encrypted_key = await self.task_repo.get_user_encrypted_assembly_key(self.db, user_id)
        youtube_cookie_status = await self.get_user_youtube_cookie_status(user_id)
        return {
            "has_assembly_key": bool(encrypted_key),
            **youtube_cookie_status,
        }

    async def save_user_assembly_key(self, user_id: str, assembly_api_key: str) -> None:
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")
        encrypted = self.secret_service.encrypt(assembly_api_key)
        await self.task_repo.set_user_encrypted_assembly_key(self.db, user_id, encrypted)

    async def clear_user_assembly_key(self, user_id: str) -> None:
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")
        await self.task_repo.clear_user_encrypted_assembly_key(self.db, user_id)

    async def save_user_youtube_cookies_from_upload(
        self,
        user_id: str,
        *,
        filename: str,
        payload: bytes,
    ) -> Dict[str, Any]:
        sanitized_filename, cookies_text = self.validate_youtube_cookies_upload(filename, payload)
        return await self.save_user_youtube_cookies(user_id, sanitized_filename, cookies_text)

    async def get_user_ai_settings(self, user_id: str) -> Dict[str, Any]:
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")
        result: Dict[str, Any] = {}
        for provider in AI_KEY_REQUIRED_PROVIDERS:
            encrypted = await self.task_repo.get_user_encrypted_ai_key(self.db, user_id, provider)
            result[f"has_{provider}_key"] = bool(encrypted)
        zai_profiles = await self.task_repo.list_user_ai_key_profiles(self.db, user_id, "zai")
        result["has_zai_subscription_key"] = bool(zai_profiles.get("subscription"))
        result["has_zai_metered_key"] = bool(zai_profiles.get("metered"))
        result["zai_routing_mode"] = await self.task_repo.get_user_zai_routing_mode(self.db, user_id)
        result["has_zai_key"] = bool(
            result.get("has_zai_key")
            or result["has_zai_subscription_key"]
            or result["has_zai_metered_key"]
        )
        saved_ollama_base_url = await self.task_repo.get_user_ollama_base_url(self.db, user_id)
        normalized_saved_ollama_base_url = self._normalize_base_url(saved_ollama_base_url)
        normalized_env_ollama_base_url = self._normalize_base_url(config.ollama_base_url)
        profiles = await self.task_repo.list_user_ollama_profiles(self.db, user_id)
        default_profile = await self.task_repo.get_user_default_ollama_profile(self.db, user_id)
        try:
            effective_ollama_settings = await self._resolve_effective_ollama_settings(user_id=user_id)
        except ValueError as resolution_error:
            logger.warning("Failed to resolve effective Ollama settings for user %s: %s", user_id, resolution_error)
            effective_ollama_settings = {
                "base_url": normalized_saved_ollama_base_url or normalized_env_ollama_base_url or DEFAULT_OLLAMA_BASE_URL,
                **(await self._resolve_ollama_request_controls(user_id=user_id)),
            }
        raw_user_controls = await self.task_repo.get_user_ollama_request_controls(self.db, user_id)
        result["ollama_profiles"] = [
            {
                "profile_name": str(profile.get("profile_name") or ""),
                "base_url": str(profile.get("base_url") or ""),
                "auth_mode": str(profile.get("auth_mode") or "none"),
                "auth_header_name": profile.get("auth_header_name"),
                "enabled": bool(profile.get("enabled", True)),
                "is_default": bool(profile.get("is_default", False)),
                "has_auth_secret": bool(profile.get("has_auth_secret", False)),
            }
            for profile in profiles
        ]
        result["default_ollama_profile"] = default_profile
        result["has_ollama_profiles"] = bool(profiles)
        result["ollama_auth_modes"] = sorted(SUPPORTED_OLLAMA_AUTH_MODES)
        result["ollama_request_controls"] = {
            "timeout_seconds": int(effective_ollama_settings["timeout_seconds"]),
            "max_retries": int(effective_ollama_settings["max_retries"]),
            "retry_backoff_ms": int(effective_ollama_settings["retry_backoff_ms"]),
        }
        result["ollama_user_request_control_overrides"] = {
            "timeout_seconds": raw_user_controls.get("timeout_seconds"),
            "max_retries": raw_user_controls.get("max_retries"),
            "retry_backoff_ms": raw_user_controls.get("retry_backoff_ms"),
        }
        result["has_ollama_server"] = bool(profiles) or bool(normalized_saved_ollama_base_url)
        result["has_env_ollama"] = bool(normalized_env_ollama_base_url)
        result["ollama_server_url"] = str(effective_ollama_settings["base_url"])
        return result

    async def save_user_ai_key(self, user_id: str, provider: str, api_key: str) -> None:
        normalized_provider = (provider or "").strip().lower()
        if normalized_provider not in AI_KEY_REQUIRED_PROVIDERS:
            raise ValueError(f"Unsupported AI provider: {provider}")
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")
        encrypted = self.secret_service.encrypt(api_key)
        await self.task_repo.set_user_encrypted_ai_key(self.db, user_id, normalized_provider, encrypted)

    async def clear_user_ai_key(self, user_id: str, provider: str) -> None:
        normalized_provider = (provider or "").strip().lower()
        if normalized_provider not in AI_KEY_REQUIRED_PROVIDERS:
            raise ValueError(f"Unsupported AI provider: {provider}")
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")
        await self.task_repo.clear_user_encrypted_ai_key(self.db, user_id, normalized_provider)

    async def save_user_ollama_base_url(self, user_id: str, base_url: str) -> str:
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")
        normalized_base_url = self._normalize_ollama_base_url(base_url)
        existing_default_profile = await self.task_repo.get_user_ollama_profile(
            self.db,
            user_id,
            DEFAULT_OLLAMA_PROFILE_NAME,
            include_secret=True,
        )
        saved_profile = await self.task_repo.set_user_ollama_profile(
            self.db,
            user_id=user_id,
            profile_name=DEFAULT_OLLAMA_PROFILE_NAME,
            base_url=normalized_base_url,
            auth_mode=(
                str(existing_default_profile.get("auth_mode") or "none")
                if existing_default_profile
                else "none"
            ),
            auth_header_name=(
                existing_default_profile.get("auth_header_name")
                if existing_default_profile
                else None
            ),
            auth_secret_encrypted=None,
            replace_auth_secret=False,
            enabled=True,
            set_as_default=True,
        )
        return str(saved_profile.get("base_url") or normalized_base_url)

    async def clear_user_ollama_base_url(self, user_id: str) -> None:
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")
        default_profile = await self.task_repo.get_user_default_ollama_profile(self.db, user_id)
        if default_profile:
            deleted = await self.task_repo.delete_user_ollama_profile(self.db, user_id, default_profile)
            if deleted:
                return
        await self.task_repo.clear_user_ollama_base_url(self.db, user_id)

    async def get_user_ollama_profiles(self, user_id: str) -> Dict[str, Any]:
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")
        profiles = await self.task_repo.list_user_ollama_profiles(self.db, user_id)
        default_profile = await self.task_repo.get_user_default_ollama_profile(self.db, user_id)
        controls = await self._resolve_ollama_request_controls(user_id=user_id)
        raw_controls = await self.task_repo.get_user_ollama_request_controls(self.db, user_id)
        return {
            "profiles": [
                {
                    "profile_name": str(profile.get("profile_name") or ""),
                    "base_url": str(profile.get("base_url") or ""),
                    "auth_mode": str(profile.get("auth_mode") or "none"),
                    "auth_header_name": profile.get("auth_header_name"),
                    "enabled": bool(profile.get("enabled", True)),
                    "is_default": bool(profile.get("is_default", False)),
                    "has_auth_secret": bool(profile.get("has_auth_secret", False)),
                }
                for profile in profiles
            ],
            "default_profile": default_profile,
            "auth_modes": sorted(SUPPORTED_OLLAMA_AUTH_MODES),
            "request_controls": controls,
            "user_request_control_overrides": {
                "timeout_seconds": raw_controls.get("timeout_seconds"),
                "max_retries": raw_controls.get("max_retries"),
                "retry_backoff_ms": raw_controls.get("retry_backoff_ms"),
            },
        }

    async def save_user_ollama_profile(
        self,
        user_id: str,
        *,
        profile_name: str,
        base_url: str,
        auth_mode: str = "none",
        auth_header_name: Optional[str] = None,
        auth_token: Optional[str] = None,
        clear_auth_token: bool = False,
        enabled: bool = True,
        set_as_default: bool = False,
    ) -> Dict[str, Any]:
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")
        normalized_profile_name = self._normalize_ollama_profile_name(profile_name)
        if not normalized_profile_name:
            raise ValueError("profile_name is required")
        normalized_base_url = self._normalize_ollama_base_url(base_url)
        normalized_auth_mode = self._normalize_ollama_auth_mode(auth_mode)
        normalized_auth_header_name = self._normalize_ollama_auth_header_name(auth_header_name)
        existing_profile = await self.task_repo.get_user_ollama_profile(
            self.db,
            user_id,
            normalized_profile_name,
            include_secret=False,
        )

        replace_auth_secret = bool(clear_auth_token)
        encrypted_auth_secret: Optional[str] = None
        normalized_token = (auth_token or "").strip()

        if normalized_auth_mode == "none":
            normalized_auth_header_name = None
            replace_auth_secret = True
        elif normalized_auth_mode == "bearer":
            normalized_auth_header_name = None
            if normalized_token:
                replace_auth_secret = True
        elif normalized_auth_mode == "custom_header":
            if not normalized_auth_header_name:
                raise ValueError("auth_header_name is required for custom_header auth mode")
            if normalized_token:
                replace_auth_secret = True

        if (
            normalized_auth_mode != "none"
            and not normalized_token
            and not bool((existing_profile or {}).get("has_auth_secret"))
            and not replace_auth_secret
        ):
            raise ValueError("auth_token is required when enabling authenticated Ollama profile")

        if normalized_token:
            encrypted_auth_secret = self.secret_service.encrypt(normalized_token)

        saved_profile = await self.task_repo.set_user_ollama_profile(
            self.db,
            user_id=user_id,
            profile_name=normalized_profile_name,
            base_url=normalized_base_url,
            auth_mode=normalized_auth_mode,
            auth_header_name=normalized_auth_header_name,
            auth_secret_encrypted=encrypted_auth_secret,
            replace_auth_secret=replace_auth_secret,
            enabled=bool(enabled),
            set_as_default=bool(set_as_default),
        )
        return {
            "profile_name": str(saved_profile.get("profile_name") or normalized_profile_name),
            "base_url": str(saved_profile.get("base_url") or normalized_base_url),
            "auth_mode": str(saved_profile.get("auth_mode") or normalized_auth_mode),
            "auth_header_name": saved_profile.get("auth_header_name"),
            "enabled": bool(saved_profile.get("enabled", True)),
            "is_default": bool(saved_profile.get("is_default", False)),
            "has_auth_secret": bool(saved_profile.get("has_auth_secret", False)),
        }

    async def delete_user_ollama_profile(self, user_id: str, profile_name: str) -> bool:
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")
        normalized_profile_name = self._normalize_ollama_profile_name(profile_name)
        if not normalized_profile_name:
            raise ValueError("profile_name is required")
        return await self.task_repo.delete_user_ollama_profile(self.db, user_id, normalized_profile_name)

    async def set_user_default_ollama_profile(self, user_id: str, profile_name: str) -> str:
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")
        normalized_profile_name = self._normalize_ollama_profile_name(profile_name)
        if not normalized_profile_name:
            raise ValueError("profile_name is required")
        return await self.task_repo.set_user_default_ollama_profile(self.db, user_id, normalized_profile_name)

    async def set_user_ollama_request_controls(
        self,
        user_id: str,
        *,
        timeout_seconds: Optional[int] = None,
        max_retries: Optional[int] = None,
        retry_backoff_ms: Optional[int] = None,
    ) -> Dict[str, int]:
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")
        normalized_timeout = self._normalize_ollama_request_control(
            timeout_seconds,
            field_name="timeout_seconds",
            minimum=MIN_OLLAMA_TIMEOUT_SECONDS,
            maximum=MAX_OLLAMA_TIMEOUT_SECONDS,
        )
        normalized_retries = self._normalize_ollama_request_control(
            max_retries,
            field_name="max_retries",
            minimum=MIN_OLLAMA_MAX_RETRIES,
            maximum=MAX_OLLAMA_MAX_RETRIES,
        )
        normalized_backoff = self._normalize_ollama_request_control(
            retry_backoff_ms,
            field_name="retry_backoff_ms",
            minimum=MIN_OLLAMA_RETRY_BACKOFF_MS,
            maximum=MAX_OLLAMA_RETRY_BACKOFF_MS,
        )
        await self.task_repo.set_user_ollama_request_controls(
            self.db,
            user_id,
            timeout_seconds=normalized_timeout,
            max_retries=normalized_retries,
            retry_backoff_ms=normalized_backoff,
        )
        return await self._resolve_ollama_request_controls(user_id=user_id)

    async def test_ollama_connection(
        self,
        user_id: str,
        *,
        profile_name: Optional[str] = None,
        base_url: Optional[str] = None,
        auth_mode: Optional[str] = None,
        auth_header_name: Optional[str] = None,
        auth_token: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        max_retries: Optional[int] = None,
        retry_backoff_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")

        resolved = await self._resolve_effective_ollama_settings(
            user_id=user_id,
            requested_profile=profile_name,
            requested_base_url=base_url,
            requested_timeout_seconds=timeout_seconds,
            requested_max_retries=max_retries,
            requested_retry_backoff_ms=retry_backoff_ms,
        )
        auth_headers = dict(resolved.get("auth_headers") or {})
        if auth_mode is not None or auth_header_name is not None or auth_token is not None:
            normalized_auth_mode = self._normalize_ollama_auth_mode(auth_mode or "none")
            normalized_auth_header_name = self._normalize_ollama_auth_header_name(auth_header_name)
            auth_headers = self._resolve_ollama_auth_headers(
                auth_mode=normalized_auth_mode,
                auth_header_name=normalized_auth_header_name,
                auth_secret_value=(auth_token or "").strip(),
            )

        result = await asyncio.to_thread(
            run_ollama_connection_test,
            str(resolved["base_url"]),
            auth_headers,
            int(resolved["timeout_seconds"]),
            int(resolved["max_retries"]),
            int(resolved["retry_backoff_ms"]),
        )
        result["ollama_profile"] = resolved.get("profile_name")
        return result

    async def ensure_ollama_recommended_model(
        self,
        user_id: str,
        *,
        profile_name: Optional[str] = None,
        base_url: Optional[str] = None,
        auth_mode: Optional[str] = None,
        auth_header_name: Optional[str] = None,
        auth_token: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        max_retries: Optional[int] = None,
        retry_backoff_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")

        resolved = await self._resolve_effective_ollama_settings(
            user_id=user_id,
            requested_profile=profile_name,
            requested_base_url=base_url,
            requested_timeout_seconds=timeout_seconds,
            requested_max_retries=max_retries,
            requested_retry_backoff_ms=retry_backoff_ms,
        )

        auth_headers = dict(resolved.get("auth_headers") or {})
        if auth_mode is not None or auth_header_name is not None or auth_token is not None:
            normalized_auth_mode = self._normalize_ollama_auth_mode(auth_mode or "none")
            normalized_auth_header_name = self._normalize_ollama_auth_header_name(auth_header_name)
            auth_headers = self._resolve_ollama_auth_headers(
                auth_mode=normalized_auth_mode,
                auth_header_name=normalized_auth_header_name,
                auth_secret_value=(auth_token or "").strip(),
            )

        effective_controls, model_preset = self._apply_ollama_model_request_preset(
            timeout_seconds=int(resolved["timeout_seconds"]),
            max_retries=int(resolved["max_retries"]),
            retry_backoff_ms=int(resolved["retry_backoff_ms"]),
            model_name=OLLAMA_RECOMMENDED_MODEL,
        )
        connection_result = await asyncio.to_thread(
            run_ollama_connection_test,
            str(resolved["base_url"]),
            auth_headers,
            int(effective_controls["timeout_seconds"]),
            int(effective_controls["max_retries"]),
            int(effective_controls["retry_backoff_ms"]),
        )
        if not connection_result.get("connected"):
            raise RuntimeError(str(connection_result.get("failure_reason") or "Could not connect to Ollama server."))

        available_models = list(connection_result.get("models") or [])
        already_available = OLLAMA_RECOMMENDED_MODEL in available_models
        pulled = False
        pull_result: Optional[Dict[str, Any]] = None

        if not already_available:
            pull_timeout_seconds = max(120, min(1800, int(effective_controls["timeout_seconds"]) * 20))
            pull_result = await asyncio.to_thread(
                run_ollama_model_pull,
                str(resolved["base_url"]),
                OLLAMA_RECOMMENDED_MODEL,
                auth_headers,
                pull_timeout_seconds,
                int(effective_controls["max_retries"]),
                int(effective_controls["retry_backoff_ms"]),
            )
            refreshed_connection_result = await asyncio.to_thread(
                run_ollama_connection_test,
                str(resolved["base_url"]),
                auth_headers,
                int(effective_controls["timeout_seconds"]),
                int(effective_controls["max_retries"]),
                int(effective_controls["retry_backoff_ms"]),
            )
            if not refreshed_connection_result.get("connected"):
                raise RuntimeError(
                    str(refreshed_connection_result.get("failure_reason") or "Could not reconnect to Ollama server.")
                )
            available_models = list(refreshed_connection_result.get("models") or [])
            if OLLAMA_RECOMMENDED_MODEL not in available_models:
                raise RuntimeError(
                    f"Ollama pull completed but model '{OLLAMA_RECOMMENDED_MODEL}' is still unavailable."
                )
            pulled = True

        return {
            "provider": "ollama",
            "status": "ok",
            "server_url": str(resolved["base_url"]),
            "ollama_profile": resolved.get("profile_name"),
            "model": OLLAMA_RECOMMENDED_MODEL,
            "already_available": already_available,
            "pulled": pulled,
            "model_count": len(available_models),
            "models": available_models,
            "request_controls": {
                "timeout_seconds": int(effective_controls["timeout_seconds"]),
                "max_retries": int(effective_controls["max_retries"]),
                "retry_backoff_ms": int(effective_controls["retry_backoff_ms"]),
            },
            "model_request_preset": model_preset,
            "pull_result": pull_result,
        }

    async def test_ollama_model_viability(
        self,
        user_id: str,
        *,
        model: str,
        attempts: int = DEFAULT_OLLAMA_VIABILITY_ATTEMPTS,
        transcript_sample: Optional[str] = None,
        profile_name: Optional[str] = None,
        base_url: Optional[str] = None,
        auth_mode: Optional[str] = None,
        auth_header_name: Optional[str] = None,
        auth_token: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        max_retries: Optional[int] = None,
        retry_backoff_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")

        normalized_model = str(model or "").strip()
        if not normalized_model:
            raise ValueError("model is required")

        normalized_attempts = self._normalize_ollama_request_control(
            attempts,
            field_name="attempts",
            minimum=MIN_OLLAMA_VIABILITY_ATTEMPTS,
            maximum=MAX_OLLAMA_VIABILITY_ATTEMPTS,
        ) or DEFAULT_OLLAMA_VIABILITY_ATTEMPTS

        sample_transcript = (
            str(transcript_sample).strip()
            if isinstance(transcript_sample, str) and transcript_sample.strip()
            else DEFAULT_OLLAMA_VIABILITY_TRANSCRIPT
        )

        resolved = await self._resolve_effective_ollama_settings(
            user_id=user_id,
            requested_profile=profile_name,
            requested_base_url=base_url,
            requested_timeout_seconds=timeout_seconds,
            requested_max_retries=max_retries,
            requested_retry_backoff_ms=retry_backoff_ms,
        )

        auth_headers = dict(resolved.get("auth_headers") or {})
        if auth_mode is not None or auth_header_name is not None or auth_token is not None:
            normalized_auth_mode = self._normalize_ollama_auth_mode(auth_mode or "none")
            normalized_auth_header_name = self._normalize_ollama_auth_header_name(auth_header_name)
            auth_headers = self._resolve_ollama_auth_headers(
                auth_mode=normalized_auth_mode,
                auth_header_name=normalized_auth_header_name,
                auth_secret_value=(auth_token or "").strip(),
            )

        effective_controls, model_preset = self._apply_ollama_model_request_preset(
            timeout_seconds=int(resolved["timeout_seconds"]),
            max_retries=int(resolved["max_retries"]),
            retry_backoff_ms=int(resolved["retry_backoff_ms"]),
            model_name=normalized_model,
        )

        connection_result = await asyncio.to_thread(
            run_ollama_connection_test,
            str(resolved["base_url"]),
            auth_headers,
            int(effective_controls["timeout_seconds"]),
            int(effective_controls["max_retries"]),
            int(effective_controls["retry_backoff_ms"]),
        )
        available_models = list(connection_result.get("models") or [])
        model_available = normalized_model in available_models

        attempt_results: List[Dict[str, Any]] = []
        successful_attempts = 0
        timeout_failures = 0
        validation_failures = 0
        ai_request_options, _preset = self._build_ollama_request_options(
            profile_name=resolved.get("profile_name"),
            auth_mode=resolved.get("auth_mode"),
            auth_headers=auth_headers,
            timeout_seconds=int(resolved["timeout_seconds"]),
            max_retries=int(resolved["max_retries"]),
            retry_backoff_ms=int(resolved["retry_backoff_ms"]),
            model_name=normalized_model,
        )

        if connection_result.get("connected") and model_available:
            from ..ai import get_most_relevant_parts_by_transcript

            per_attempt_timeout_seconds = max(
                45,
                min(240, int(ai_request_options["ollama_timeout_seconds"]) + 60),
            )

            for attempt_index in range(1, normalized_attempts + 1):
                started_at = time.perf_counter()
                try:
                    analysis = await asyncio.wait_for(
                        get_most_relevant_parts_by_transcript(
                            sample_transcript,
                            ai_provider="ollama",
                            ai_api_key=None,
                            ai_base_url=str(resolved["base_url"]),
                            ai_model=normalized_model,
                            ai_request_options=ai_request_options,
                        ),
                        timeout=per_attempt_timeout_seconds,
                    )
                    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
                    diagnostics = analysis.diagnostics if isinstance(analysis.diagnostics, dict) else {}
                    diagnostics_error = str(diagnostics.get("error") or "").strip() or None
                    selected_segments = len(analysis.most_relevant_segments or [])
                    attempt_ok = diagnostics_error is None and selected_segments > 0
                    if diagnostics_error is not None:
                        validation_failures += 1
                    if attempt_ok:
                        successful_attempts += 1
                    attempt_results.append(
                        {
                            "attempt": attempt_index,
                            "ok": attempt_ok,
                            "latency_ms": elapsed_ms,
                            "selected_segments": selected_segments,
                            "summary_preview": str(analysis.summary or "")[:180],
                            "diagnostics_error": diagnostics_error,
                            "diagnostics_error_type": diagnostics.get("error_type"),
                        }
                    )
                except asyncio.TimeoutError:
                    timeout_failures += 1
                    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
                    attempt_results.append(
                        {
                            "attempt": attempt_index,
                            "ok": False,
                            "latency_ms": elapsed_ms,
                            "selected_segments": 0,
                            "summary_preview": "",
                            "diagnostics_error": "viability attempt timed out",
                            "diagnostics_error_type": "TimeoutError",
                        }
                    )
                except Exception as exc:
                    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
                    validation_failures += 1
                    attempt_results.append(
                        {
                            "attempt": attempt_index,
                            "ok": False,
                            "latency_ms": elapsed_ms,
                            "selected_segments": 0,
                            "summary_preview": "",
                            "diagnostics_error": str(exc),
                            "diagnostics_error_type": type(exc).__name__,
                        }
                    )

        viable = bool(connection_result.get("connected")) and model_available and successful_attempts > 0
        if viable:
            status = "ok"
            reason = "Model passed structured analysis viability checks."
        elif not connection_result.get("connected"):
            status = "error"
            reason = str(connection_result.get("failure_reason") or "Could not connect to Ollama server.")
        elif not model_available:
            status = "error"
            reason = f"Model '{normalized_model}' is not available on the selected Ollama server."
        elif timeout_failures == normalized_attempts:
            status = "error"
            reason = (
                "All viability attempts timed out. Increase Ollama timeout/request controls or use a faster model."
            )
        elif validation_failures > 0:
            status = "error"
            reason = (
                "Model responded, but structured-output validation failed during transcript analysis."
            )
        else:
            status = "error"
            reason = "Model did not produce viable clip segments."

        return {
            "provider": "ollama",
            "status": status,
            "viable": viable,
            "reason": reason,
            "server_url": str(resolved["base_url"]),
            "ollama_profile": resolved.get("profile_name"),
            "model": normalized_model,
            "checks": {
                "connection": {
                    "ok": bool(connection_result.get("connected")),
                    "failure_reason": connection_result.get("failure_reason"),
                    "failure_status_code": connection_result.get("failure_status_code"),
                },
                "model_available": {
                    "ok": model_available,
                    "available_models": available_models,
                },
                "structured_analysis": {
                    "ok": successful_attempts > 0,
                    "attempts": normalized_attempts,
                    "successful_attempts": successful_attempts,
                    "timeout_failures": timeout_failures,
                    "validation_failures": validation_failures,
                    "sample_transcript_char_count": len(sample_transcript),
                },
            },
            "attempt_results": attempt_results,
            "request_controls": {
                "timeout_seconds": int(ai_request_options["ollama_timeout_seconds"]),
                "max_retries": int(ai_request_options["ollama_max_retries"]),
                "retry_backoff_ms": int(ai_request_options["ollama_retry_backoff_ms"]),
            },
            "model_request_preset": model_preset,
        }

    async def get_effective_ollama_base_url(
        self,
        user_id: str,
        requested_base_url: Optional[str] = None,
    ) -> str:
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")
        return await self._resolve_effective_ollama_base_url(
            user_id=user_id,
            requested_base_url=requested_base_url,
        )

    async def list_available_ai_models(
        self,
        user_id: str,
        provider: str,
        zai_routing_mode: Optional[str] = None,
        ollama_base_url: Optional[str] = None,
        ollama_profile: Optional[str] = None,
        ollama_timeout_seconds: Optional[int] = None,
        ollama_max_retries: Optional[int] = None,
        ollama_retry_backoff_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        normalized_provider = (provider or "").strip().lower()
        if normalized_provider not in SUPPORTED_AI_PROVIDERS:
            raise ValueError(f"Unsupported AI provider: {provider}")
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")

        resolved_routing_mode: Optional[str] = None
        resolved_ollama_base_url: Optional[str] = None
        if normalized_provider == "ollama":
            resolved_ollama = await self._resolve_effective_ollama_settings(
                user_id=user_id,
                requested_base_url=ollama_base_url,
                requested_profile=ollama_profile,
                requested_timeout_seconds=ollama_timeout_seconds,
                requested_max_retries=ollama_max_retries,
                requested_retry_backoff_ms=ollama_retry_backoff_ms,
            )
            resolved_ollama_base_url = str(resolved_ollama["base_url"])
            models = await asyncio.to_thread(
                list_models_for_provider,
                normalized_provider,
                "",
                resolved_ollama_base_url,
                dict(resolved_ollama.get("auth_headers") or {}),
                int(resolved_ollama["timeout_seconds"]),
                int(resolved_ollama["max_retries"]),
                int(resolved_ollama["retry_backoff_ms"]),
            )
            default_model = DEFAULT_AI_MODELS[normalized_provider]
            return {
                "provider": normalized_provider,
                "models": models,
                "default_model": default_model,
                "count": len(models),
                "zai_routing_mode": None,
                "ollama_server_url": resolved_ollama_base_url,
                "ollama_profile": resolved_ollama.get("profile_name"),
                "ollama_request_controls": {
                    "timeout_seconds": int(resolved_ollama["timeout_seconds"]),
                    "max_retries": int(resolved_ollama["max_retries"]),
                    "retry_backoff_ms": int(resolved_ollama["retry_backoff_ms"]),
                },
            }

        key_attempts, resolved_routing_mode = await self.get_effective_user_ai_api_key_attempts(
            user_id=user_id,
            provider=normalized_provider,
            zai_routing_mode=zai_routing_mode,
        )
        api_key = key_attempts[0]["key"] if key_attempts else None
        if not api_key:
            routing_hint = f" (routing mode: {resolved_routing_mode})" if resolved_routing_mode else ""
            raise ValueError(
                f"{normalized_provider} selected but no API key is configured{routing_hint}. Save one in Settings."
            )

        models = await asyncio.to_thread(
            list_models_for_provider,
            normalized_provider,
            api_key,
        )
        default_model = DEFAULT_AI_MODELS[normalized_provider]
        return {
            "provider": normalized_provider,
            "models": models,
            "default_model": default_model,
            "count": len(models),
            "zai_routing_mode": resolved_routing_mode,
        }

    async def get_task_with_clips(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task details with all clips."""
        task = await self.task_repo.get_task_by_id(self.db, task_id)

        if not task:
            return None

        clips = await self.clip_repo.get_clips_by_task(self.db, task_id)
        task["clips"] = clips
        task["clips_count"] = len(clips)
        task["diagnostics"] = {
            "queue_target": task.get("runtime_info", {}).get("queue_target"),
            "worker_type": task.get("runtime_info", {}).get("worker_type"),
            "transcription": {
                "provider": task.get("transcription_provider"),
                "model": task.get("runtime_info", {}).get("whisper_model_size"),
                "device_preference": task.get("runtime_info", {}).get("whisper_device"),
            },
            "ai": {
                "provider": task.get("ai_provider"),
                "model": task.get("runtime_info", {}).get("ai_model"),
            },
            "runtime_target": task.get("runtime_info", {}).get("runtime_target"),
            "fallback_reason": task.get("runtime_info", {}).get("fallback_reason"),
            "current_stage": task.get("runtime_info", {}).get("current_stage"),
            "latest_stage_metadata": task.get("runtime_info", {}).get("latest_stage_metadata"),
        }

        return task

    async def get_user_tasks(self, user_id: str, limit: int = 50) -> list[Dict[str, Any]]:
        """Get all tasks for a user."""
        return await self.task_repo.get_user_tasks(self.db, user_id, limit)

    async def delete_task(self, task_id: str) -> None:
        """Delete a task and all its associated clips."""
        await self.clip_repo.delete_clips_by_task(self.db, task_id)
        await self.draft_clip_repo.delete_drafts_by_task(self.db, task_id)
        await self.task_repo.delete_task(self.db, task_id)
        logger.info(f"Deleted task {task_id} and all associated clips")

    async def delete_all_user_tasks(self, user_id: str) -> int:
        """Delete all tasks that belong to a user."""
        deleted_count = await self.task_repo.delete_tasks_by_user(self.db, user_id)
        logger.info(f"Deleted all tasks for user {user_id}: {deleted_count}")
        return deleted_count
