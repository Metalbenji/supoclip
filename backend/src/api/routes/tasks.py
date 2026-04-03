"""
Task API routes using refactored architecture.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse
from typing import Optional, Any, Dict, List
import json
import logging
import mimetypes
import re
from uuid import UUID

from ...database import get_db
from ...services.task_service import DEFAULT_AI_MODELS, DraftOverlapError, TaskService
from ...services.ai_model_catalog_service import ModelCatalogError
from ...workers.job_queue import JobQueue
from ...workers.progress import ProgressTracker
from ...config import Config
from ...ai_focus_tags import normalize_ai_focus_tags
from ...subtitle_style import DEFAULT_SUBTITLE_STYLE, normalize_subtitle_style
from ...task_subtitle_style import build_normalized_subtitle_style_for_task
from ...transcription_limits import (
    ASSEMBLYAI_MAX_DURATION_SECONDS,
    ASSEMBLYAI_MAX_LOCAL_UPLOAD_SIZE_BYTES,
    ASSEMBLYAI_MAX_REMOTE_FILE_SIZE_BYTES,
)
import redis.asyncio as redis

logger = logging.getLogger(__name__)
config = Config()
router = APIRouter(prefix="/tasks", tags=["tasks"])
SUPPORTED_TRANSCRIPTION_PROVIDERS = {"local", "assemblyai"}
SUPPORTED_WHISPER_DEVICE_PREFERENCES = {"auto", "cpu", "gpu"}
SUPPORTED_WHISPER_MODEL_SIZES = {"tiny", "base", "small", "medium", "large", "turbo"}
SUPPORTED_AI_PROVIDERS = {"openai", "google", "anthropic", "zai", "ollama"}
AI_KEY_REQUIRED_PROVIDERS = {"openai", "google", "anthropic", "zai"}
SUPPORTED_ZAI_KEY_PROFILES = {"subscription", "metered"}
SUPPORTED_ZAI_ROUTING_MODES = {"auto", "subscription", "metered"}
SUPPORTED_OLLAMA_AUTH_MODES = {"none", "bearer", "custom_header"}
OLLAMA_PROFILE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,99}$")
MIN_OLLAMA_TIMEOUT_SECONDS = 1
MAX_OLLAMA_TIMEOUT_SECONDS = 600
MIN_OLLAMA_MAX_RETRIES = 0
MAX_OLLAMA_MAX_RETRIES = 10
MIN_OLLAMA_RETRY_BACKOFF_MS = 0
MAX_OLLAMA_RETRY_BACKOFF_MS = 30000
MIN_OLLAMA_VIABILITY_ATTEMPTS = 1
MAX_OLLAMA_VIABILITY_ATTEMPTS = 3
MIN_WHISPER_CHUNK_DURATION_SECONDS = 300
MAX_WHISPER_CHUNK_DURATION_SECONDS = 3600
MIN_WHISPER_CHUNK_OVERLAP_SECONDS = 0
MAX_WHISPER_CHUNK_OVERLAP_SECONDS = 120
MIN_WHISPER_GPU_INDEX = 0
MIN_TASK_TIMEOUT_SECONDS = 300
MAX_TASK_TIMEOUT_SECONDS = 86400
SUPPORTED_FRAMING_MODE_OVERRIDES = {"auto", "prefer_face", "fixed_position"}
DRAFT_UPDATE_FIELDS = {"id", "start_time", "end_time", "edited_text", "is_selected", "framing_mode_override"}
DRAFT_CREATE_FIELDS = {"start_time", "end_time", "edited_text", "is_selected", "framing_mode_override"}
SUBTITLE_STYLE_FIELDS = set(DEFAULT_SUBTITLE_STYLE.keys())
MAX_SUBTITLE_STYLE_BACKFILL_LIMIT = 1000
OLLAMA_AUTO_PULL_MODEL = DEFAULT_AI_MODELS["ollama"]
OLLAMA_CREATE_TASK_PREFLIGHT_TRANSCRIPT = """[00:00 - 00:12] A clear opening promise makes people keep watching.
[00:12 - 00:24] Give one concrete example quickly so the claim feels real.
[00:24 - 00:38] Keep each clip focused on a single idea with one practical takeaway.
[00:38 - 00:52] End with one action viewers can apply immediately."""


def _build_overlap_error_detail(error: DraftOverlapError) -> Dict[str, Any]:
    return {
        "message": str(error),
        "overlap_conflicts": error.conflicts,
    }


def _coerce_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _resolve_review_before_render_enabled(raw: object) -> bool:
    return _coerce_bool(raw, default=True)


def _resolve_framing_mode_override(raw: object) -> str:
    normalized = str(raw or "auto").strip().lower()
    if normalized == "disable_face_crop":
        normalized = "fixed_position"
    if normalized not in SUPPORTED_FRAMING_MODE_OVERRIDES:
        raise HTTPException(
            status_code=400,
            detail=(
                "framing_mode_override must be one of "
                + ", ".join(sorted(SUPPORTED_FRAMING_MODE_OVERRIDES))
            ),
        )
    return normalized


def _resolve_timeline_editor_enabled(raw: object) -> bool:
    return _coerce_bool(raw, default=True)


def _resolve_transcription_provider(raw: object) -> str:
    if not isinstance(raw, str):
        return "local"
    provider = raw.strip().lower()
    if provider not in SUPPORTED_TRANSCRIPTION_PROVIDERS:
        return "local"
    return provider


def _coerce_int(raw: object, field_name: str) -> int:
    if isinstance(raw, bool):
        raise HTTPException(status_code=400, detail=f"{field_name} must be an integer")
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} must be an integer") from exc


def _resolve_task_timeout_seconds(raw: object) -> Optional[int]:
    if raw is None:
        return None
    timeout_seconds = _coerce_int(raw, "transcription_options.task_timeout_seconds")
    if timeout_seconds < MIN_TASK_TIMEOUT_SECONDS or timeout_seconds > MAX_TASK_TIMEOUT_SECONDS:
        raise HTTPException(
            status_code=400,
            detail=(
                "transcription_options.task_timeout_seconds must be between "
                f"{MIN_TASK_TIMEOUT_SECONDS} and {MAX_TASK_TIMEOUT_SECONDS}"
            ),
        )
    worker_cap_seconds = int(getattr(config, "worker_job_timeout_seconds", 21600) or 21600)
    if timeout_seconds > worker_cap_seconds:
        raise HTTPException(
            status_code=400,
            detail=(
                "transcription_options.task_timeout_seconds exceeds worker cap "
                f"({worker_cap_seconds}). Increase WORKER_JOB_TIMEOUT_SECONDS and restart workers."
            ),
        )
    return timeout_seconds


def _resolve_whisper_device_preference(raw: object) -> Optional[str]:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise HTTPException(
            status_code=400,
            detail="transcription_options.whisper_device must be auto, cpu, or gpu",
        )
    normalized = raw.strip().lower()
    if normalized == "cuda":
        normalized = "gpu"
    if normalized not in SUPPORTED_WHISPER_DEVICE_PREFERENCES:
        raise HTTPException(
            status_code=400,
            detail="transcription_options.whisper_device must be auto, cpu, or gpu",
        )
    return normalized


def _resolve_whisper_gpu_index(raw: object) -> Optional[int]:
    if raw is None or raw == "":
        return None
    gpu_index = _coerce_int(raw, "transcription_options.whisper_gpu_index")
    if gpu_index < MIN_WHISPER_GPU_INDEX:
        raise HTTPException(
            status_code=400,
            detail=f"transcription_options.whisper_gpu_index must be >= {MIN_WHISPER_GPU_INDEX}",
        )
    return gpu_index


def _resolve_whisper_model_size(raw: object) -> Optional[str]:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise HTTPException(
            status_code=400,
            detail="transcription_options.whisper_model_size must be tiny, base, small, medium, large, or turbo",
        )
    normalized = raw.strip().lower()
    if normalized not in SUPPORTED_WHISPER_MODEL_SIZES:
        raise HTTPException(
            status_code=400,
            detail="transcription_options.whisper_model_size must be tiny, base, small, medium, large, or turbo",
        )
    return normalized


def _resolve_local_queue_name(transcription_runtime_options: Dict[str, Any]) -> str:
    whisper_device = str(transcription_runtime_options.get("whisper_device") or "auto").strip().lower()
    if whisper_device == "cuda":
        whisper_device = "gpu"
    if whisper_device == "cpu":
        return config.arq_local_queue_name
    if config.enable_gpu_worker:
        return config.arq_local_gpu_queue_name
    return config.arq_local_queue_name


def _resolve_transcription_runtime_options(
    transcription_options: Dict[str, Any],
    provider: str,
) -> Dict[str, Any]:
    options: Dict[str, Any] = {}

    task_timeout_seconds = _resolve_task_timeout_seconds(transcription_options.get("task_timeout_seconds"))
    if task_timeout_seconds is not None:
        options["task_timeout_seconds"] = task_timeout_seconds

    if provider != "local":
        return options

    if "whisper_chunking_enabled" in transcription_options:
        options["whisper_chunking_enabled"] = _coerce_bool(
            transcription_options.get("whisper_chunking_enabled"),
            default=True,
        )

    if "whisper_device" in transcription_options:
        options["whisper_device"] = _resolve_whisper_device_preference(
            transcription_options.get("whisper_device")
        )

    if "whisper_model_size" in transcription_options:
        options["whisper_model_size"] = _resolve_whisper_model_size(
            transcription_options.get("whisper_model_size")
        )

    if "whisper_gpu_index" in transcription_options:
        options["whisper_gpu_index"] = _resolve_whisper_gpu_index(
            transcription_options.get("whisper_gpu_index")
        )

    if "whisper_chunk_duration_seconds" in transcription_options:
        chunk_duration_seconds = _coerce_int(
            transcription_options.get("whisper_chunk_duration_seconds"),
            "transcription_options.whisper_chunk_duration_seconds",
        )
        if (
            chunk_duration_seconds < MIN_WHISPER_CHUNK_DURATION_SECONDS
            or chunk_duration_seconds > MAX_WHISPER_CHUNK_DURATION_SECONDS
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "transcription_options.whisper_chunk_duration_seconds must be between "
                    f"{MIN_WHISPER_CHUNK_DURATION_SECONDS} and {MAX_WHISPER_CHUNK_DURATION_SECONDS}"
                ),
            )
        options["whisper_chunk_duration_seconds"] = chunk_duration_seconds

    if "whisper_chunk_overlap_seconds" in transcription_options:
        chunk_overlap_seconds = _coerce_int(
            transcription_options.get("whisper_chunk_overlap_seconds"),
            "transcription_options.whisper_chunk_overlap_seconds",
        )
        if (
            chunk_overlap_seconds < MIN_WHISPER_CHUNK_OVERLAP_SECONDS
            or chunk_overlap_seconds > MAX_WHISPER_CHUNK_OVERLAP_SECONDS
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "transcription_options.whisper_chunk_overlap_seconds must be between "
                    f"{MIN_WHISPER_CHUNK_OVERLAP_SECONDS} and {MAX_WHISPER_CHUNK_OVERLAP_SECONDS}"
                ),
            )
        options["whisper_chunk_overlap_seconds"] = chunk_overlap_seconds

    duration_for_validation = options.get("whisper_chunk_duration_seconds")
    overlap_for_validation = options.get("whisper_chunk_overlap_seconds")
    if duration_for_validation is not None and overlap_for_validation is not None:
        if overlap_for_validation >= duration_for_validation:
            raise HTTPException(
                status_code=400,
                detail=(
                    "transcription_options.whisper_chunk_overlap_seconds must be smaller than "
                    "whisper_chunk_duration_seconds"
                ),
            )

    return options


def _default_ai_provider() -> str:
    llm_value = (config.llm or "").strip()
    if ":" in llm_value:
        provider = llm_value.split(":", 1)[0].strip().lower()
        if provider in SUPPORTED_AI_PROVIDERS:
            return provider
    return "openai"


def _resolve_ai_provider(raw: object) -> str:
    if not isinstance(raw, str):
        return _default_ai_provider()
    provider = raw.strip().lower()
    if provider not in SUPPORTED_AI_PROVIDERS:
        return _default_ai_provider()
    return provider


def _resolve_zai_routing_mode(raw: object) -> Optional[str]:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise HTTPException(status_code=400, detail="ai_options.routing_mode must be a string")
    normalized = raw.strip().lower()
    if normalized not in SUPPORTED_ZAI_ROUTING_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported z.ai routing mode: {normalized}",
        )
    return normalized


def _resolve_zai_profile(raw: object) -> str:
    if not isinstance(raw, str):
        raise HTTPException(status_code=400, detail="profile must be a string")
    profile = raw.strip().lower()
    if profile not in SUPPORTED_ZAI_KEY_PROFILES:
        raise HTTPException(status_code=400, detail=f"Unsupported z.ai key profile: {profile}")
    return profile


def _resolve_ollama_profile_name(raw: object) -> str:
    if not isinstance(raw, str):
        raise HTTPException(status_code=400, detail="profile must be a string")
    profile = raw.strip().lower()
    if not profile:
        raise HTTPException(status_code=400, detail="profile is required")
    if not OLLAMA_PROFILE_NAME_RE.match(profile):
        raise HTTPException(
            status_code=400,
            detail="profile must match [a-zA-Z0-9][a-zA-Z0-9._-]{0,99}",
        )
    return profile


def _resolve_ollama_auth_mode(raw: object, *, required: bool = False) -> Optional[str]:
    if raw is None:
        if required:
            raise HTTPException(status_code=400, detail="auth_mode is required")
        return None
    if not isinstance(raw, str):
        raise HTTPException(status_code=400, detail="auth_mode must be a string")
    auth_mode = raw.strip().lower()
    if auth_mode not in SUPPORTED_OLLAMA_AUTH_MODES:
        raise HTTPException(status_code=400, detail=f"Unsupported Ollama auth mode: {auth_mode}")
    return auth_mode


def _resolve_optional_int(
    raw: object,
    *,
    field_name: str,
    minimum: int,
    maximum: int,
) -> Optional[int]:
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise HTTPException(status_code=400, detail=f"{field_name} must be an integer")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} must be an integer") from exc
    if value < minimum or value > maximum:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must be between {minimum} and {maximum}",
        )
    return value


def _require_admin_access(request: Request) -> None:
    """
    Admin guard for destructive task-management endpoints.
    If ADMIN_API_KEY is configured, it must match x-admin-key header.
    """
    configured_admin_key = (config.admin_api_key or "").strip()
    provided_admin_key = (request.headers.get("x-admin-key") or "").strip()

    if configured_admin_key:
        if not provided_admin_key or provided_admin_key != configured_admin_key:
            raise HTTPException(status_code=403, detail="Invalid admin key")
        return

    # Backward-compatible fallback for local/dev setups without ADMIN_API_KEY.
    user_id = (request.headers.get("user_id") or "").strip()
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Admin access requires x-admin-key (recommended) or user_id header",
        )
    logger.warning("ADMIN_API_KEY is not configured; allowing admin task cancellation via user_id header.")


def _require_user_id(request: Request) -> str:
    user_id = (request.headers.get("user_id") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="User authentication required")
    return user_id


async def _read_optional_json_object(request: Request) -> Dict[str, Any]:
    try:
        raw_data = await request.json()
    except Exception:
        return {}
    if raw_data is None:
        return {}
    if not isinstance(raw_data, dict):
        raise HTTPException(status_code=400, detail="Payload must be a JSON object")
    return raw_data


def _normalize_task_id_list(raw_task_ids: Any) -> List[str]:
    if raw_task_ids is None:
        return []
    if not isinstance(raw_task_ids, list):
        raise HTTPException(status_code=400, detail="task_ids must be an array of task IDs")

    task_ids: List[str] = []
    for raw in raw_task_ids:
        if not isinstance(raw, str):
            raise HTTPException(status_code=400, detail="task_ids must contain strings")
        normalized = raw.strip()
        if not normalized:
            continue
        task_ids.append(normalized)
    return task_ids


@router.get("/")
async def list_tasks(request: Request, db: AsyncSession = Depends(get_db), limit: int = 50):
    """
    Get all tasks for the authenticated user.
    """
    headers = request.headers
    user_id = headers.get("user_id")

    if not user_id:
        raise HTTPException(status_code=401, detail="User authentication required")

    try:
        task_service = TaskService(db)
        tasks = await task_service.get_user_tasks(user_id, limit)

        return {
            "tasks": tasks,
            "total": len(tasks)
        }

    except Exception as e:
        logger.error(f"Error retrieving user tasks: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving tasks: {str(e)}")


@router.get("/transcription-settings")
async def get_transcription_settings(request: Request, db: AsyncSession = Depends(get_db)):
    """Get user transcription settings (key presence only, never returns the key)."""
    user_id = _require_user_id(request)
    try:
        from ...whisper_runtime import get_local_whisper_model_metadata, get_local_whisper_runtime_info

        task_service = TaskService(db)
        settings = await task_service.get_user_transcription_settings(user_id)
        runtime_info = get_local_whisper_runtime_info()
        return {
            "provider_options": sorted(SUPPORTED_TRANSCRIPTION_PROVIDERS),
            "local_whisper_device_options": sorted(SUPPORTED_WHISPER_DEVICE_PREFERENCES),
            "local_whisper_model_options": ["turbo", "medium", "large", "small", "base", "tiny"],
            "local_whisper_models": get_local_whisper_model_metadata(),
            "gpu_worker_enabled": bool(config.enable_gpu_worker),
            "has_assembly_key": bool(settings.get("has_assembly_key")),
            "has_env_fallback": bool((config.assembly_ai_api_key or "").strip()),
            "assemblyai_max_duration_seconds": ASSEMBLYAI_MAX_DURATION_SECONDS,
            "assemblyai_max_local_upload_size_bytes": ASSEMBLYAI_MAX_LOCAL_UPLOAD_SIZE_BYTES,
            "assemblyai_max_remote_file_size_bytes": ASSEMBLYAI_MAX_REMOTE_FILE_SIZE_BYTES,
            "assemblyai_limit_behavior": "fallback_to_local",
            "worker_timeout_cap_seconds": int(getattr(config, "worker_job_timeout_seconds", 21600) or 21600),
            "min_task_timeout_seconds": MIN_TASK_TIMEOUT_SECONDS,
            "max_task_timeout_seconds": MAX_TASK_TIMEOUT_SECONDS,
            "min_whisper_chunk_duration_seconds": MIN_WHISPER_CHUNK_DURATION_SECONDS,
            "max_whisper_chunk_duration_seconds": MAX_WHISPER_CHUNK_DURATION_SECONDS,
            "min_whisper_chunk_overlap_seconds": MIN_WHISPER_CHUNK_OVERLAP_SECONDS,
            "max_whisper_chunk_overlap_seconds": MAX_WHISPER_CHUNK_OVERLAP_SECONDS,
            "local_whisper_runtime": runtime_info,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving transcription settings: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving settings: {str(e)}")


@router.put("/transcription-settings/assembly-key")
async def save_assembly_key(request: Request, db: AsyncSession = Depends(get_db)):
    """Save user AssemblyAI API key (encrypted at rest)."""
    user_id = _require_user_id(request)
    data = await request.json()
    api_key = str(data.get("assembly_api_key") or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="assembly_api_key is required")

    try:
        task_service = TaskService(db)
        await task_service.save_user_assembly_key(user_id, api_key)
        return {"message": "AssemblyAI key saved", "has_assembly_key": True}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error saving AssemblyAI key: {e}")
        raise HTTPException(status_code=500, detail=f"Error saving key: {str(e)}")


@router.delete("/transcription-settings/assembly-key")
async def delete_assembly_key(request: Request, db: AsyncSession = Depends(get_db)):
    """Delete user AssemblyAI API key."""
    user_id = _require_user_id(request)
    try:
        task_service = TaskService(db)
        await task_service.clear_user_assembly_key(user_id)
        return {"message": "AssemblyAI key removed", "has_assembly_key": False}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting AssemblyAI key: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting key: {str(e)}")


@router.get("/ai-settings")
async def get_ai_settings(request: Request, db: AsyncSession = Depends(get_db)):
    """Get user AI-provider settings (key presence only, never returns keys)."""
    user_id = _require_user_id(request)
    try:
        task_service = TaskService(db)
        settings = await task_service.get_user_ai_settings(user_id)
        return {
            "provider_options": sorted(SUPPORTED_AI_PROVIDERS),
            "default_provider": _default_ai_provider(),
            "has_openai_key": bool(settings.get("has_openai_key")),
            "has_google_key": bool(settings.get("has_google_key")),
            "has_anthropic_key": bool(settings.get("has_anthropic_key")),
            "has_zai_key": bool(settings.get("has_zai_key")),
            "has_ollama_server": bool(settings.get("has_ollama_server")),
            "has_zai_subscription_key": bool(settings.get("has_zai_subscription_key")),
            "has_zai_metered_key": bool(settings.get("has_zai_metered_key")),
            "zai_routing_mode": str(settings.get("zai_routing_mode") or "auto"),
            "zai_routing_options": sorted(SUPPORTED_ZAI_ROUTING_MODES),
            "has_env_openai": bool((config.openai_api_key or "").strip()),
            "has_env_google": bool((config.google_api_key or "").strip()),
            "has_env_anthropic": bool((config.anthropic_api_key or "").strip()),
            "has_env_zai": bool((config.zai_api_key or "").strip()),
            "has_env_ollama": bool(settings.get("has_env_ollama")),
            "ollama_server_url": str(settings.get("ollama_server_url") or config.ollama_base_url or ""),
            "has_ollama_profiles": bool(settings.get("has_ollama_profiles")),
            "ollama_profiles": settings.get("ollama_profiles") or [],
            "default_ollama_profile": settings.get("default_ollama_profile"),
            "ollama_auth_modes": settings.get("ollama_auth_modes") or sorted(SUPPORTED_OLLAMA_AUTH_MODES),
            "ollama_request_controls": settings.get("ollama_request_controls") or {},
            "ollama_user_request_control_overrides": settings.get("ollama_user_request_control_overrides") or {},
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving AI settings: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving AI settings: {str(e)}")


@router.put("/ai-settings/{provider}/key")
async def save_ai_provider_key(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Save user API key for selected AI provider (encrypted at rest)."""
    user_id = _require_user_id(request)
    provider = (provider or "").strip().lower()
    if provider not in AI_KEY_REQUIRED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported AI provider: {provider}")
    data = await request.json()
    api_key = str(data.get("api_key") or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key is required")

    try:
        task_service = TaskService(db)
        await task_service.save_user_ai_key(user_id, provider, api_key)
        return {"message": f"{provider} key saved", "provider": provider}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error saving AI provider key: {e}")
        raise HTTPException(status_code=500, detail=f"Error saving key: {str(e)}")


@router.delete("/ai-settings/{provider}/key")
async def delete_ai_provider_key(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Delete user API key for selected AI provider."""
    user_id = _require_user_id(request)
    provider = (provider or "").strip().lower()
    if provider not in AI_KEY_REQUIRED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported AI provider: {provider}")
    try:
        task_service = TaskService(db)
        await task_service.clear_user_ai_key(user_id, provider)
        return {"message": f"{provider} key removed", "provider": provider}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting AI provider key: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting key: {str(e)}")


@router.put("/ai-settings/ollama/server")
async def save_ollama_server(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Save per-user Ollama server base URL."""
    user_id = _require_user_id(request)
    data = await request.json()
    server_url = str(data.get("server_url") or "").strip()
    if not server_url:
        raise HTTPException(status_code=400, detail="server_url is required")

    try:
        task_service = TaskService(db)
        normalized_server_url = await task_service.save_user_ollama_base_url(user_id, server_url)
        return {"message": "ollama server saved", "provider": "ollama", "server_url": normalized_server_url}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error saving Ollama server URL: {e}")
        raise HTTPException(status_code=500, detail=f"Error saving Ollama server URL: {str(e)}")


@router.delete("/ai-settings/ollama/server")
async def delete_ollama_server(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Delete per-user Ollama server base URL."""
    user_id = _require_user_id(request)
    try:
        task_service = TaskService(db)
        await task_service.clear_user_ollama_base_url(user_id)
        return {"message": "ollama server removed", "provider": "ollama"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting Ollama server URL: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting Ollama server URL: {str(e)}")


@router.get("/ai-settings/ollama/profiles")
async def list_ollama_profiles(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """List per-user Ollama server profiles."""
    user_id = _require_user_id(request)
    try:
        task_service = TaskService(db)
        return await task_service.get_user_ollama_profiles(user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error listing Ollama profiles: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing Ollama profiles: {str(e)}")


@router.put("/ai-settings/ollama/profiles/{profile}")
async def save_ollama_profile(
    profile: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Create or update a per-user Ollama server profile."""
    user_id = _require_user_id(request)
    normalized_profile = _resolve_ollama_profile_name(profile)
    data = await _read_optional_json_object(request)
    base_url = str(data.get("base_url") or data.get("server_url") or "").strip()
    if not base_url:
        raise HTTPException(status_code=400, detail="base_url is required")

    auth_mode = _resolve_ollama_auth_mode(data.get("auth_mode")) or "none"
    auth_header_name = (
        str(data.get("auth_header_name")).strip()
        if data.get("auth_header_name") is not None
        else None
    )
    auth_token = (
        str(data.get("auth_token")).strip()
        if data.get("auth_token") is not None
        else None
    )
    clear_auth_token = bool(data.get("clear_auth_token", False))
    enabled = bool(data.get("enabled", True))
    set_as_default = bool(data.get("set_as_default", False))

    try:
        task_service = TaskService(db)
        saved_profile = await task_service.save_user_ollama_profile(
            user_id,
            profile_name=normalized_profile,
            base_url=base_url,
            auth_mode=auth_mode,
            auth_header_name=auth_header_name,
            auth_token=auth_token,
            clear_auth_token=clear_auth_token,
            enabled=enabled,
            set_as_default=set_as_default,
        )
        return {
            "message": "ollama profile saved",
            "profile": saved_profile,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error saving Ollama profile {normalized_profile}: {e}")
        raise HTTPException(status_code=500, detail=f"Error saving Ollama profile: {str(e)}")


@router.delete("/ai-settings/ollama/profiles/{profile}")
async def delete_ollama_profile(
    profile: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Delete a per-user Ollama server profile."""
    user_id = _require_user_id(request)
    normalized_profile = _resolve_ollama_profile_name(profile)
    try:
        task_service = TaskService(db)
        deleted = await task_service.delete_user_ollama_profile(user_id, normalized_profile)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Ollama profile not found: {normalized_profile}")
        return {
            "message": "ollama profile removed",
            "profile_name": normalized_profile,
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting Ollama profile {normalized_profile}: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting Ollama profile: {str(e)}")


@router.put("/ai-settings/ollama/default-profile")
async def set_ollama_default_profile(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Set the default per-user Ollama profile."""
    user_id = _require_user_id(request)
    data = await _read_optional_json_object(request)
    normalized_profile = _resolve_ollama_profile_name(data.get("profile"))
    try:
        task_service = TaskService(db)
        saved_profile = await task_service.set_user_default_ollama_profile(user_id, normalized_profile)
        return {
            "message": "ollama default profile saved",
            "default_profile": saved_profile,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error setting Ollama default profile {normalized_profile}: {e}")
        raise HTTPException(status_code=500, detail=f"Error saving Ollama default profile: {str(e)}")


@router.put("/ai-settings/ollama/request-controls")
async def save_ollama_request_controls(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Save user-level Ollama timeout/retry controls."""
    user_id = _require_user_id(request)
    data = await _read_optional_json_object(request)
    timeout_seconds = _resolve_optional_int(
        data.get("timeout_seconds"),
        field_name="timeout_seconds",
        minimum=MIN_OLLAMA_TIMEOUT_SECONDS,
        maximum=MAX_OLLAMA_TIMEOUT_SECONDS,
    )
    max_retries = _resolve_optional_int(
        data.get("max_retries"),
        field_name="max_retries",
        minimum=MIN_OLLAMA_MAX_RETRIES,
        maximum=MAX_OLLAMA_MAX_RETRIES,
    )
    retry_backoff_ms = _resolve_optional_int(
        data.get("retry_backoff_ms"),
        field_name="retry_backoff_ms",
        minimum=MIN_OLLAMA_RETRY_BACKOFF_MS,
        maximum=MAX_OLLAMA_RETRY_BACKOFF_MS,
    )
    if timeout_seconds is None and max_retries is None and retry_backoff_ms is None:
        raise HTTPException(status_code=400, detail="At least one request control is required")

    try:
        task_service = TaskService(db)
        resolved = await task_service.set_user_ollama_request_controls(
            user_id,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            retry_backoff_ms=retry_backoff_ms,
        )
        return {"message": "ollama request controls saved", "request_controls": resolved}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error saving Ollama request controls: {e}")
        raise HTTPException(status_code=500, detail=f"Error saving Ollama request controls: {str(e)}")


@router.post("/ai-settings/ollama/test-connection")
async def test_ollama_connection(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Test connectivity to the resolved Ollama profile/base URL."""
    user_id = _require_user_id(request)
    data = await _read_optional_json_object(request)
    profile = (
        _resolve_ollama_profile_name(data.get("profile"))
        if data.get("profile") is not None
        else None
    )
    base_url = str(data.get("base_url") or data.get("server_url") or "").strip() or None
    auth_mode = _resolve_ollama_auth_mode(data.get("auth_mode")) if data.get("auth_mode") is not None else None
    auth_header_name = (
        str(data.get("auth_header_name")).strip()
        if data.get("auth_header_name") is not None
        else None
    )
    auth_token = (
        str(data.get("auth_token")).strip()
        if data.get("auth_token") is not None
        else None
    )
    timeout_seconds = _resolve_optional_int(
        data.get("timeout_seconds"),
        field_name="timeout_seconds",
        minimum=MIN_OLLAMA_TIMEOUT_SECONDS,
        maximum=MAX_OLLAMA_TIMEOUT_SECONDS,
    )
    max_retries = _resolve_optional_int(
        data.get("max_retries"),
        field_name="max_retries",
        minimum=MIN_OLLAMA_MAX_RETRIES,
        maximum=MAX_OLLAMA_MAX_RETRIES,
    )
    retry_backoff_ms = _resolve_optional_int(
        data.get("retry_backoff_ms"),
        field_name="retry_backoff_ms",
        minimum=MIN_OLLAMA_RETRY_BACKOFF_MS,
        maximum=MAX_OLLAMA_RETRY_BACKOFF_MS,
    )

    try:
        task_service = TaskService(db)
        result = await task_service.test_ollama_connection(
            user_id,
            profile_name=profile,
            base_url=base_url,
            auth_mode=auth_mode,
            auth_header_name=auth_header_name,
            auth_token=auth_token,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            retry_backoff_ms=retry_backoff_ms,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error testing Ollama connection: {e}")
        raise HTTPException(status_code=500, detail=f"Error testing Ollama connection: {str(e)}")


@router.post("/ai-settings/ollama/ensure-recommended-model")
async def ensure_ollama_recommended_model(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Ensure the recommended Ollama model is installed (requires explicit confirm=true)."""
    user_id = _require_user_id(request)
    data = await _read_optional_json_object(request)
    if data.get("confirm") is not True:
        raise HTTPException(
            status_code=400,
            detail="confirm=true is required to pull the recommended Ollama model",
        )

    profile = (
        _resolve_ollama_profile_name(data.get("profile"))
        if data.get("profile") is not None
        else None
    )
    base_url = str(data.get("base_url") or data.get("server_url") or "").strip() or None
    auth_mode = _resolve_ollama_auth_mode(data.get("auth_mode")) if data.get("auth_mode") is not None else None
    auth_header_name = (
        str(data.get("auth_header_name")).strip()
        if data.get("auth_header_name") is not None
        else None
    )
    auth_token = (
        str(data.get("auth_token")).strip()
        if data.get("auth_token") is not None
        else None
    )
    timeout_seconds = _resolve_optional_int(
        data.get("timeout_seconds"),
        field_name="timeout_seconds",
        minimum=MIN_OLLAMA_TIMEOUT_SECONDS,
        maximum=MAX_OLLAMA_TIMEOUT_SECONDS,
    )
    max_retries = _resolve_optional_int(
        data.get("max_retries"),
        field_name="max_retries",
        minimum=MIN_OLLAMA_MAX_RETRIES,
        maximum=MAX_OLLAMA_MAX_RETRIES,
    )
    retry_backoff_ms = _resolve_optional_int(
        data.get("retry_backoff_ms"),
        field_name="retry_backoff_ms",
        minimum=MIN_OLLAMA_RETRY_BACKOFF_MS,
        maximum=MAX_OLLAMA_RETRY_BACKOFF_MS,
    )

    try:
        task_service = TaskService(db)
        result = await task_service.ensure_ollama_recommended_model(
            user_id=user_id,
            profile_name=profile,
            base_url=base_url,
            auth_mode=auth_mode,
            auth_header_name=auth_header_name,
            auth_token=auth_token,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            retry_backoff_ms=retry_backoff_ms,
        )
        if str(result.get("model") or "").strip() != OLLAMA_AUTO_PULL_MODEL:
            raise HTTPException(status_code=500, detail="Unexpected model pulled")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ensuring recommended Ollama model: {e}")
        raise HTTPException(status_code=500, detail=f"Error ensuring recommended Ollama model: {str(e)}")


@router.post("/ai-settings/ollama/test-model-viability")
async def test_ollama_model_viability(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Test whether an Ollama model is viable for structured clip analysis."""
    user_id = _require_user_id(request)
    data = await _read_optional_json_object(request)

    model_raw = data.get("model")
    if not isinstance(model_raw, str) or not model_raw.strip():
        raise HTTPException(status_code=400, detail="model is required")
    model = model_raw.strip()

    profile = (
        _resolve_ollama_profile_name(data.get("profile"))
        if data.get("profile") is not None
        else None
    )
    base_url = str(data.get("base_url") or data.get("server_url") or "").strip() or None
    auth_mode = _resolve_ollama_auth_mode(data.get("auth_mode")) if data.get("auth_mode") is not None else None
    auth_header_name = (
        str(data.get("auth_header_name")).strip()
        if data.get("auth_header_name") is not None
        else None
    )
    auth_token = (
        str(data.get("auth_token")).strip()
        if data.get("auth_token") is not None
        else None
    )
    timeout_seconds = _resolve_optional_int(
        data.get("timeout_seconds"),
        field_name="timeout_seconds",
        minimum=MIN_OLLAMA_TIMEOUT_SECONDS,
        maximum=MAX_OLLAMA_TIMEOUT_SECONDS,
    )
    max_retries = _resolve_optional_int(
        data.get("max_retries"),
        field_name="max_retries",
        minimum=MIN_OLLAMA_MAX_RETRIES,
        maximum=MAX_OLLAMA_MAX_RETRIES,
    )
    retry_backoff_ms = _resolve_optional_int(
        data.get("retry_backoff_ms"),
        field_name="retry_backoff_ms",
        minimum=MIN_OLLAMA_RETRY_BACKOFF_MS,
        maximum=MAX_OLLAMA_RETRY_BACKOFF_MS,
    )
    attempts = _resolve_optional_int(
        data.get("attempts"),
        field_name="attempts",
        minimum=MIN_OLLAMA_VIABILITY_ATTEMPTS,
        maximum=MAX_OLLAMA_VIABILITY_ATTEMPTS,
    )

    transcript_sample: Optional[str] = None
    if data.get("transcript_sample") is not None:
        if not isinstance(data.get("transcript_sample"), str):
            raise HTTPException(status_code=400, detail="transcript_sample must be a string")
        transcript_sample = str(data.get("transcript_sample")).strip() or None

    try:
        task_service = TaskService(db)
        return await task_service.test_ollama_model_viability(
            user_id=user_id,
            model=model,
            attempts=attempts or 2,
            transcript_sample=transcript_sample,
            profile_name=profile,
            base_url=base_url,
            auth_mode=auth_mode,
            auth_header_name=auth_header_name,
            auth_token=auth_token,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            retry_backoff_ms=retry_backoff_ms,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error testing Ollama model viability: {e}")
        raise HTTPException(status_code=500, detail=f"Error testing Ollama model viability: {str(e)}")


@router.put("/ai-settings/zai/profiles/{profile}/key")
async def save_zai_profile_key(
    profile: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Save z.ai profile key (subscription or metered)."""
    user_id = _require_user_id(request)
    normalized_profile = _resolve_zai_profile(profile)
    data = await request.json()
    api_key = str(data.get("api_key") or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key is required")

    try:
        task_service = TaskService(db)
        await task_service.save_user_ai_profile_key(
            user_id=user_id,
            provider="zai",
            profile_name=normalized_profile,
            api_key=api_key,
        )
        return {"message": f"zai {normalized_profile} key saved", "provider": "zai", "profile": normalized_profile}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error saving z.ai profile key: {e}")
        raise HTTPException(status_code=500, detail=f"Error saving key: {str(e)}")


@router.delete("/ai-settings/zai/profiles/{profile}/key")
async def delete_zai_profile_key(
    profile: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Delete z.ai profile key (subscription or metered)."""
    user_id = _require_user_id(request)
    normalized_profile = _resolve_zai_profile(profile)
    try:
        task_service = TaskService(db)
        await task_service.clear_user_ai_profile_key(
            user_id=user_id,
            provider="zai",
            profile_name=normalized_profile,
        )
        return {"message": f"zai {normalized_profile} key removed", "provider": "zai", "profile": normalized_profile}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting z.ai profile key: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting key: {str(e)}")


@router.put("/ai-settings/zai/routing-mode")
async def set_zai_routing_mode(request: Request, db: AsyncSession = Depends(get_db)):
    """Set default z.ai key routing mode for the user."""
    user_id = _require_user_id(request)
    data = await request.json()
    routing_mode = _resolve_zai_routing_mode(data.get("routing_mode"))
    if routing_mode is None:
        raise HTTPException(status_code=400, detail="routing_mode is required")

    try:
        task_service = TaskService(db)
        saved_mode = await task_service.set_user_zai_routing_mode(user_id, routing_mode)
        return {"message": "z.ai routing mode saved", "routing_mode": saved_mode}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error saving z.ai routing mode: {e}")
        raise HTTPException(status_code=500, detail=f"Error saving routing mode: {str(e)}")


@router.get("/ai-settings/{provider}/models")
async def list_ai_provider_models(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """List provider models using saved user provider settings (or env/default fallback)."""
    user_id = _require_user_id(request)
    provider = (provider or "").strip().lower()
    if provider not in SUPPORTED_AI_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported AI provider: {provider}")

    zai_routing_mode = (
        _resolve_zai_routing_mode(request.query_params.get("routing_mode"))
        if provider == "zai"
        else None
    )
    ollama_server_url = (
        (request.query_params.get("server_url") or "").strip()
        if provider == "ollama"
        else None
    )
    ollama_profile = (
        _resolve_ollama_profile_name(request.query_params.get("profile"))
        if provider == "ollama" and request.query_params.get("profile") is not None
        else None
    )
    ollama_timeout_seconds = (
        _resolve_optional_int(
            request.query_params.get("timeout_seconds"),
            field_name="timeout_seconds",
            minimum=MIN_OLLAMA_TIMEOUT_SECONDS,
            maximum=MAX_OLLAMA_TIMEOUT_SECONDS,
        )
        if provider == "ollama"
        else None
    )
    ollama_max_retries = (
        _resolve_optional_int(
            request.query_params.get("max_retries"),
            field_name="max_retries",
            minimum=MIN_OLLAMA_MAX_RETRIES,
            maximum=MAX_OLLAMA_MAX_RETRIES,
        )
        if provider == "ollama"
        else None
    )
    ollama_retry_backoff_ms = (
        _resolve_optional_int(
            request.query_params.get("retry_backoff_ms"),
            field_name="retry_backoff_ms",
            minimum=MIN_OLLAMA_RETRY_BACKOFF_MS,
            maximum=MAX_OLLAMA_RETRY_BACKOFF_MS,
        )
        if provider == "ollama"
        else None
    )

    try:
        task_service = TaskService(db)
        result = await task_service.list_available_ai_models(
            user_id,
            provider,
            zai_routing_mode=zai_routing_mode,
            ollama_base_url=ollama_server_url,
            ollama_profile=ollama_profile,
            ollama_timeout_seconds=ollama_timeout_seconds,
            ollama_max_retries=ollama_max_retries,
            ollama_retry_backoff_ms=ollama_retry_backoff_ms,
        )
        return result
    except ModelCatalogError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except ValueError as e:
        message = str(e)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message)
        raise HTTPException(status_code=400, detail=message)
    except Exception as e:
        logger.error(f"Error listing AI provider models for provider={provider}: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing models: {str(e)}")


@router.post("/")
async def create_task(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Create a new task and enqueue it for processing.
    Returns task_id immediately.
    """
    data = await request.json()
    headers = request.headers

    raw_source = data.get("source")
    user_id = headers.get("user_id")

    # Get and normalize subtitle options
    font_options = data.get("font_options", {})
    if not isinstance(font_options, dict):
        font_options = {}
    subtitle_style = normalize_subtitle_style(font_options)
    font_family = subtitle_style["font_family"]
    font_size = subtitle_style["font_size"]
    font_color = subtitle_style["font_color"]
    transitions_enabled = _coerce_bool(font_options.get("transitions_enabled"), default=False)
    transcription_options = data.get("transcription_options", {})
    if not isinstance(transcription_options, dict):
        transcription_options = {}
    transcription_provider = _resolve_transcription_provider(
        transcription_options.get("provider", "local")
    )
    transcription_runtime_options = _resolve_transcription_runtime_options(
        transcription_options,
        transcription_provider,
    )
    ai_options = data.get("ai_options", {})
    if not isinstance(ai_options, dict):
        ai_options = {}
    ai_provider = _resolve_ai_provider(ai_options.get("provider", _default_ai_provider()))
    ai_routing_mode = (
        _resolve_zai_routing_mode(ai_options.get("routing_mode"))
        if ai_provider == "zai"
        else None
    )
    ai_model_raw = ai_options.get("model")
    if ai_model_raw is None:
        ai_model = None
    elif isinstance(ai_model_raw, str):
        ai_model = ai_model_raw.strip() or None
    else:
        raise HTTPException(status_code=400, detail="ai_options.model must be a string")
    try:
        ai_focus_tags = normalize_ai_focus_tags(ai_options.get("focus_tags"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not user_id:
        raise HTTPException(status_code=401, detail="User authentication required")

    if "review_before_render_enabled" in data:
        review_before_render_enabled = _resolve_review_before_render_enabled(data.get("review_before_render_enabled"))
    else:
        task_service_for_defaults = TaskService(db)
        review_before_render_enabled = (
            await task_service_for_defaults.task_repo.get_user_default_review_before_render_enabled(
                db,
                user_id,
            )
        )
    if "timeline_editor_enabled" in data:
        timeline_editor_enabled = _resolve_timeline_editor_enabled(data.get("timeline_editor_enabled"))
    else:
        task_service_for_defaults = TaskService(db)
        timeline_editor_enabled = await task_service_for_defaults.task_repo.get_user_default_timeline_editor_enabled(
            db,
            user_id,
        )

    if not raw_source or not raw_source.get("url"):
        raise HTTPException(status_code=400, detail="Source URL is required")

    try:
        task_service = TaskService(db)

        # Create task
        if transcription_provider == "assemblyai":
            settings = await task_service.get_user_transcription_settings(user_id)
            has_saved_key = bool(settings.get("has_assembly_key"))
            has_env_key = bool((config.assembly_ai_api_key or "").strip())
            if not (has_saved_key or has_env_key):
                raise HTTPException(
                    status_code=400,
                    detail="AssemblyAI selected but no API key is configured. Save one in Settings.",
                )
        resolved_zai_routing_mode: Optional[str] = None
        if ai_provider in AI_KEY_REQUIRED_PROVIDERS:
            ai_key_attempts, resolved_zai_routing_mode = await task_service.get_effective_user_ai_api_key_attempts(
                user_id=user_id,
                provider=ai_provider,
                zai_routing_mode=ai_routing_mode,
            )
            if not ai_key_attempts:
                routing_detail = f" (routing mode: {resolved_zai_routing_mode})" if resolved_zai_routing_mode else ""
                raise HTTPException(
                    status_code=400,
                    detail=f"{ai_provider} selected but no API key is configured{routing_detail}. Save one in Settings.",
                )
        elif ai_provider == "ollama":
            await task_service.get_effective_ollama_base_url(user_id)
            resolved_ollama_model = ai_model or DEFAULT_AI_MODELS["ollama"]
            viability = await task_service.test_ollama_model_viability(
                user_id=user_id,
                model=resolved_ollama_model,
                attempts=1,
                transcript_sample=OLLAMA_CREATE_TASK_PREFLIGHT_TRANSCRIPT,
            )
            if not bool(viability.get("viable")):
                failure_reason = str(viability.get("reason") or "model failed viability check")
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Ollama model '{resolved_ollama_model}' failed preflight viability check: {failure_reason}. "
                        "Run /tasks/ai-settings/ollama/test-model-viability in Settings to inspect and switch to a viable model."
                    ),
                )
            ai_model = resolved_ollama_model

        task_id = await task_service.create_task_with_source(
            user_id=user_id,
            url=raw_source["url"],
            title=raw_source.get("title"),
            font_family=font_family,
            font_size=font_size,
            font_color=font_color,
            subtitle_style=subtitle_style,
            transitions_enabled=transitions_enabled,
            transcription_provider=transcription_provider,
            ai_provider=ai_provider,
            ai_focus_tags=ai_focus_tags,
            review_before_render_enabled=review_before_render_enabled,
            timeline_editor_enabled=timeline_editor_enabled,
        )

        # Get source type for worker
        source_type = task_service.video_service.determine_source_type(raw_source["url"])

        queue_name = (
            config.arq_assembly_queue_name
            if transcription_provider == "assemblyai"
            else _resolve_local_queue_name(transcription_runtime_options)
        )

        # Enqueue job for worker
        try:
            job_id = await JobQueue.enqueue_job(
                "process_video_task",
                task_id,
                raw_source["url"],
                source_type,
                user_id,
                font_family,
                font_size,
                font_color,
                transitions_enabled,
                transcription_provider,
                ai_provider,
                ai_model,
                subtitle_style,
                resolved_zai_routing_mode,
                transcription_runtime_options,
                queue_name=queue_name,
            )
        except Exception as enqueue_error:
            logger.error(f"Failed to enqueue job for task {task_id}: {enqueue_error}")
            await task_service.task_repo.update_task_status(
                db,
                task_id,
                "error",
                progress_message="Failed to enqueue processing job"
            )
            raise HTTPException(status_code=503, detail="Failed to queue task for processing")

        logger.info(f"Task {task_id} created and job {job_id} enqueued")

        return {
            "task_id": task_id,
            "job_id": job_id,
            "transcription_provider": transcription_provider,
            "transcription_options": transcription_runtime_options,
            "ai_provider": ai_provider,
            "ai_routing_mode": resolved_zai_routing_mode,
            "ai_focus_tags": ai_focus_tags,
            "review_before_render_enabled": review_before_render_enabled,
            "timeline_editor_enabled": timeline_editor_enabled,
            "message": "Task created and queued for processing"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating task: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating task: {str(e)}")


@router.post("/admin/cancel-all")
async def cancel_all_tasks(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Admin action: cancel all queued/processing tasks and drain ARQ queue keys.
    """
    _require_admin_access(request)

    try:
        task_service = TaskService(db)
        cancelled_task_ids = await task_service.task_repo.cancel_active_tasks(
            db,
            progress_message="Cancelled by admin action",
        )
        cancel_flags_set = await JobQueue.mark_tasks_cancelled(cancelled_task_ids)
        queue_summary = await JobQueue.cancel_all_jobs()

        logger.info(
            "Admin cancelled tasks: tasks=%s cancel_flags=%s queue_removed=%s job_keys_deleted=%s",
            len(cancelled_task_ids),
            cancel_flags_set,
            queue_summary.get("queue_entries_removed", 0),
            queue_summary.get("job_keys_deleted", 0),
        )

        return {
            "message": "Cancellation completed",
            "cancelled_task_count": len(cancelled_task_ids),
            "cancelled_task_ids": cancelled_task_ids,
            "cancel_flags_set": cancel_flags_set,
            "queue_summary": queue_summary,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling all tasks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error cancelling tasks: {str(e)}")


@router.post("/admin/backfill-awaiting-review-subtitle-styles")
async def backfill_awaiting_review_subtitle_styles(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Backfill missing/partial tasks.subtitle_style for awaiting_review tasks.
    Uses task font fields + user default style values as reconstruction sources.
    """
    _require_admin_access(request)
    data = await _read_optional_json_object(request)

    dry_run = _coerce_bool(data.get("dry_run"), default=False)
    include_existing = _coerce_bool(data.get("include_existing"), default=False)
    user_filter = str(data.get("user_id") or "").strip() or None
    task_ids = _normalize_task_id_list(data.get("task_ids"))

    raw_limit = data.get("limit")
    if raw_limit is None:
        limit = None
    else:
        limit = _coerce_int(raw_limit, "limit")
        if limit < 1 or limit > MAX_SUBTITLE_STYLE_BACKFILL_LIMIT:
            raise HTTPException(
                status_code=400,
                detail=f"limit must be between 1 and {MAX_SUBTITLE_STYLE_BACKFILL_LIMIT}",
            )

    task_service = TaskService(db)
    task_rows = await task_service.task_repo.get_tasks_for_subtitle_style_backfill(
        db,
        statuses=["awaiting_review"],
        user_id=user_filter,
        task_ids=task_ids or None,
        include_existing=include_existing,
        limit=limit,
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

    if dry_run:
        updated_count = len(updates)
    else:
        updated_count = await task_service.task_repo.update_task_subtitle_styles_bulk(db, updates)

    updated_task_ids = list(updates.keys())
    return {
        "message": "Subtitle style backfill complete" if not dry_run else "Subtitle style backfill dry run complete",
        "dry_run": dry_run,
        "scanned_tasks": len(task_rows),
        "would_update_tasks": len(updates),
        "updated_tasks": updated_count,
        "unchanged_tasks": unchanged_count,
        "updated_task_ids_preview": updated_task_ids[:25],
    }


@router.patch("/admin/{task_id}/subtitle-style")
async def patch_task_subtitle_style(task_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Admin endpoint for patching one task's subtitle_style.
    Defaults to merge payload with existing style and requires awaiting_review status.
    """
    _require_admin_access(request)
    data = await _read_optional_json_object(request)

    merge_with_existing = _coerce_bool(data.get("merge_with_existing"), default=True)
    dry_run = _coerce_bool(data.get("dry_run"), default=False)
    allow_non_review = _coerce_bool(data.get("allow_non_review"), default=False)

    if "subtitle_style" in data:
        raw_style = data.get("subtitle_style")
    else:
        control_fields = {"merge_with_existing", "dry_run", "allow_non_review"}
        if any(field in data for field in control_fields):
            raise HTTPException(status_code=400, detail="subtitle_style is required when control fields are provided")
        raw_style = data

    if not isinstance(raw_style, dict) or not raw_style:
        raise HTTPException(status_code=400, detail="subtitle_style must be a non-empty object")

    unknown_fields = set(raw_style.keys()) - SUBTITLE_STYLE_FIELDS
    if unknown_fields:
        unknown_list = ", ".join(sorted(unknown_fields))
        raise HTTPException(status_code=400, detail=f"Unsupported subtitle_style fields: {unknown_list}")

    task_service = TaskService(db)
    task_rows = await task_service.task_repo.get_tasks_for_subtitle_style_backfill(
        db,
        statuses=[],
        task_ids=[task_id],
        include_existing=True,
        limit=1,
    )
    if not task_rows:
        raise HTTPException(status_code=404, detail="Task not found")

    task_row = task_rows[0]
    task_status = str(task_row.get("status") or "")
    if task_status != "awaiting_review" and not allow_non_review:
        raise HTTPException(
            status_code=400,
            detail="Task subtitle_style patching is limited to awaiting_review tasks unless allow_non_review=true",
        )

    normalized_style = build_normalized_subtitle_style_for_task(
        task_row,
        patch=raw_style,
        merge_with_existing=merge_with_existing,
    )

    if dry_run:
        updated = False
    else:
        updated = await task_service.task_repo.update_task_subtitle_style(db, task_id, normalized_style)
        if not updated:
            raise HTTPException(status_code=404, detail="Task not found")

    return {
        "task_id": task_id,
        "status": task_status,
        "dry_run": dry_run,
        "merge_with_existing": merge_with_existing,
        "subtitle_style": normalized_style,
        "updated": updated,
    }


@router.delete("/")
async def delete_all_user_tasks(request: Request, db: AsyncSession = Depends(get_db)):
    """Delete all tasks for the authenticated user."""
    user_id = request.headers.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User authentication required")

    try:
        task_service = TaskService(db)
        deleted_count = await task_service.delete_all_user_tasks(user_id)
        return {
            "message": "All tasks deleted successfully",
            "deleted_count": deleted_count,
        }
    except Exception as e:
        logger.error(f"Error deleting all user tasks: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting all tasks: {str(e)}")


@router.get("/{task_id}")
async def get_task(task_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Get task details."""
    # EventSource in browsers cannot set custom headers, so allow query fallback.
    user_id = request.headers.get("user_id") or request.query_params.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User authentication required")

    try:
        task_service = TaskService(db)
        task = await task_service.get_task_with_clips(task_id)

        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        if task["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to access this task")

        return task

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving task: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving task: {str(e)}")


@router.get("/{task_id}/source-video")
async def get_task_source_video(task_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Serve source video file for interactive timeline review."""
    user_id = request.headers.get("user_id") or request.query_params.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User authentication required")

    task_service = TaskService(db)
    task = await task_service.task_repo.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this task")

    source_url = str(task.get("source_url") or "").strip()
    source_type = str(task.get("source_type") or "").strip()
    if not source_url or not source_type:
        raise HTTPException(status_code=400, detail="Task source is missing")

    try:
        source_video_path = await task_service.video_service.resolve_video_path(
            url=source_url,
            source_type=source_type,
        )
    except Exception as e:
        logger.error(f"Error resolving source video for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to prepare source video for review")

    media_type = mimetypes.guess_type(str(source_video_path))[0] or "video/mp4"
    return FileResponse(
        path=str(source_video_path),
        media_type=media_type,
        filename=source_video_path.name,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{task_id}/waveform")
async def get_task_waveform(
    task_id: str,
    request: Request,
    bins: int = Query(default=3000, ge=300, le=12000),
    start_seconds: Optional[float] = Query(default=None, ge=0),
    end_seconds: Optional[float] = Query(default=None, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Return waveform peaks for the task source video used in timeline review."""
    user_id = request.headers.get("user_id") or request.query_params.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User authentication required")

    task_service = TaskService(db)
    task = await task_service.task_repo.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this task")

    source_url = str(task.get("source_url") or "").strip()
    source_type = str(task.get("source_type") or "").strip()
    if not source_url or not source_type:
        raise HTTPException(status_code=400, detail="Task source is missing")
    if (
        start_seconds is not None
        and end_seconds is not None
        and float(end_seconds) <= float(start_seconds)
    ):
        raise HTTPException(status_code=400, detail="end_seconds must be greater than start_seconds")

    try:
        source_video_path = await task_service.video_service.resolve_video_path(
            url=source_url,
            source_type=source_type,
        )
        waveform = await task_service.video_service.get_waveform_data(
            source_video_path,
            bins=bins,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
        )
        return {
            "task_id": task_id,
            **waveform,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error building waveform for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to build waveform")


@router.get("/{task_id}/clips")
async def get_task_clips(task_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Get all clips for a task."""
    user_id = request.headers.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User authentication required")

    try:
        task_service = TaskService(db)
        task = await task_service.get_task_with_clips(task_id)

        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        if task["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to access this task")

        return {
            "task_id": task_id,
            "clips": task.get("clips", []),
            "total_clips": len(task.get("clips", []))
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving clips: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving clips: {str(e)}")


@router.get("/{task_id}/draft-clips")
async def get_task_draft_clips(task_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Get editable draft clips for a task in awaiting_review state."""
    user_id = request.headers.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User authentication required")

    try:
        task_service = TaskService(db)
        task = await task_service.task_repo.get_task_by_id(db, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        if task["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to access this task")

        draft_clips = await task_service.get_task_draft_clips(task_id)
        return {
            "task_id": task_id,
            "status": task.get("status"),
            "draft_clips": draft_clips,
            "total_drafts": len(draft_clips),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving draft clips: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving draft clips: {str(e)}")


@router.put("/{task_id}/draft-clips")
async def update_task_draft_clips(task_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Bulk update draft clip timing/text/selection before finalizing."""
    user_id = request.headers.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User authentication required")

    task_service = TaskService(db)
    task = await task_service.task_repo.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this task")
    if task.get("status") != "awaiting_review":
        raise HTTPException(status_code=400, detail="Draft clips can only be edited while task is awaiting_review")

    data = await request.json()
    draft_clips = data.get("draft_clips")
    if not isinstance(draft_clips, list) or len(draft_clips) == 0:
        raise HTTPException(status_code=400, detail="draft_clips must be a non-empty list")

    for item in draft_clips:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="Each draft clip update must be an object")
        unknown_fields = set(item.keys()) - DRAFT_UPDATE_FIELDS
        if unknown_fields:
            unknown_list = ", ".join(sorted(unknown_fields))
            raise HTTPException(status_code=400, detail=f"Unsupported draft clip fields: {unknown_list}")

    try:
        updated_drafts = await task_service.update_task_draft_clips(task_id, draft_clips)
        return {
            "task_id": task_id,
            "draft_clips": updated_drafts,
            "total_drafts": len(updated_drafts),
            "message": "Draft clips updated",
        }
    except DraftOverlapError as e:
        raise HTTPException(status_code=400, detail=_build_overlap_error_detail(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating draft clips: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating draft clips: {str(e)}")


@router.post("/{task_id}/draft-clips")
async def create_task_draft_clip(task_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Create a new draft clip during review."""
    user_id = request.headers.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User authentication required")

    task_service = TaskService(db)
    task = await task_service.task_repo.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this task")
    if task.get("status") != "awaiting_review":
        raise HTTPException(status_code=400, detail="Draft clips can only be created while task is awaiting_review")

    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Payload must be an object")
    unknown_fields = set(data.keys()) - DRAFT_CREATE_FIELDS
    if unknown_fields:
        unknown_list = ", ".join(sorted(unknown_fields))
        raise HTTPException(status_code=400, detail=f"Unsupported draft clip fields: {unknown_list}")

    start_time = str(data.get("start_time") or "").strip()
    end_time = str(data.get("end_time") or "").strip()
    if not start_time or not end_time:
        raise HTTPException(status_code=400, detail="start_time and end_time are required")

    source_url = str(task.get("source_url") or "").strip()
    source_type = str(task.get("source_type") or "").strip()
    if not source_url or not source_type:
        raise HTTPException(status_code=400, detail="Task source is missing")

    try:
        created_draft = await task_service.create_task_draft_clip(
            task_id=task_id,
            start_time=start_time,
            end_time=end_time,
            source_url=source_url,
            source_type=source_type,
            user_id=str(task.get("user_id") or user_id),
            edited_text=data.get("edited_text"),
            is_selected=(
                _coerce_bool(data.get("is_selected"), default=False)
                if "is_selected" in data
                else None
            ),
            framing_mode_override=(
                _resolve_framing_mode_override(data.get("framing_mode_override"))
                if "framing_mode_override" in data
                else None
            ),
        )
        return {
            "task_id": task_id,
            "draft_clip": created_draft,
            "message": "Draft clip created",
        }
    except DraftOverlapError as e:
        raise HTTPException(status_code=400, detail=_build_overlap_error_detail(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating draft clip: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating draft clip: {str(e)}")


@router.delete("/{task_id}/draft-clips/{draft_id}")
async def delete_task_draft_clip(
    task_id: str,
    draft_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a draft clip during review."""
    user_id = request.headers.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User authentication required")

    task_service = TaskService(db)
    task = await task_service.task_repo.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this task")
    if task.get("status") != "awaiting_review":
        raise HTTPException(status_code=400, detail="Draft clips can only be deleted while task is awaiting_review")

    try:
        await task_service.delete_task_draft_clip(task_id=task_id, draft_id=str(draft_id))
        draft_clips = await task_service.get_task_draft_clips(task_id)
        return {
            "task_id": task_id,
            "draft_clips": draft_clips,
            "total_drafts": len(draft_clips),
            "message": "Draft clip deleted",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting draft clip: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting draft clip: {str(e)}")


@router.post("/{task_id}/draft-clips/restore")
async def restore_task_draft_clips(task_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Restore draft clips to their initial review defaults."""
    user_id = request.headers.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User authentication required")

    task_service = TaskService(db)
    task = await task_service.task_repo.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this task")
    if task.get("status") != "awaiting_review":
        raise HTTPException(status_code=400, detail="Draft clips can only be restored while task is awaiting_review")

    try:
        restored_drafts = await task_service.restore_task_draft_clips(task_id)
        return {
            "task_id": task_id,
            "draft_clips": restored_drafts,
            "total_drafts": len(restored_drafts),
            "message": "Draft clips restored to initial values",
        }
    except DraftOverlapError as e:
        raise HTTPException(status_code=400, detail=_build_overlap_error_detail(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error restoring draft clips: {e}")
        raise HTTPException(status_code=500, detail=f"Error restoring draft clips: {str(e)}")


@router.post("/{task_id}/finalize")
async def finalize_task(task_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Queue rendering from reviewed draft clips."""
    user_id = request.headers.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User authentication required")

    task_service = TaskService(db)
    task = await task_service.task_repo.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to finalize this task")
    if task.get("status") != "awaiting_review":
        raise HTTPException(status_code=400, detail="Task is not awaiting review")

    selected_count = await task_service.draft_clip_repo.count_selected_drafts(db, task_id)
    if selected_count <= 0:
        raise HTTPException(status_code=400, detail="Finalize requires at least one selected draft clip")
    selected_drafts = [
        draft
        for draft in await task_service.get_task_draft_clips(task_id)
        if draft.get("is_selected") and not draft.get("is_deleted")
    ]
    try:
        task_service._validate_non_overlapping_draft_windows(selected_drafts)
    except DraftOverlapError as e:
        raise HTTPException(status_code=400, detail=_build_overlap_error_detail(e))

    source_url = task.get("source_url")
    source_type = task.get("source_type")
    if not source_url or not source_type:
        raise HTTPException(status_code=400, detail="Task source is missing; cannot finalize")

    persisted_subtitle_style = task.get("subtitle_style")
    if isinstance(persisted_subtitle_style, dict):
        subtitle_style_seed = dict(persisted_subtitle_style)
    else:
        subtitle_style_seed = {}

    subtitle_style_seed.setdefault("font_family", task.get("font_family"))
    subtitle_style_seed.setdefault("font_size", task.get("font_size"))
    subtitle_style_seed.setdefault("font_color", task.get("font_color"))
    subtitle_style = normalize_subtitle_style(subtitle_style_seed)

    await task_service.task_repo.update_task_status(
        db,
        task_id,
        "queued",
        progress=0,
        progress_message="Queued rendering from approved draft clips...",
    )

    try:
        job_id = await JobQueue.enqueue_job(
            "process_video_task",
            task_id,
            source_url,
            source_type,
            user_id,
            subtitle_style["font_family"],
            int(subtitle_style["font_size"]),
            subtitle_style["font_color"],
            _coerce_bool(task.get("transitions_enabled"), default=False),
            task.get("transcription_provider") or "local",
            task.get("ai_provider") or _default_ai_provider(),
            None,
            subtitle_style,
            None,
            {},
            queue_name=config.arq_local_queue_name,
            render_from_drafts=True,
        )
    except Exception as enqueue_error:
        logger.error(f"Failed to enqueue finalize job for task {task_id}: {enqueue_error}")
        await task_service.task_repo.update_task_status(
            db,
            task_id,
            "awaiting_review",
            progress=100,
            progress_message="Failed to queue finalize job. Please try again.",
        )
        raise HTTPException(status_code=503, detail="Failed to queue finalize job")

    return {
        "task_id": task_id,
        "job_id": job_id,
        "selected_clips": selected_count,
        "status": "queued",
        "message": "Finalize job queued",
    }


@router.get("/{task_id}/progress")
async def get_task_progress_sse(task_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """
    SSE endpoint for real-time progress updates.
    Streams progress updates as Server-Sent Events.
    """
    # EventSource in browsers cannot set custom headers, so allow query fallback.
    user_id = request.headers.get("user_id") or request.query_params.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User authentication required")

    task_service = TaskService(db)
    task = await task_service.task_repo.get_task_by_id(db, task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this task")

    async def event_generator():
        """Generate SSE events for task progress."""
        # Send initial task status
        yield {
            "event": "status",
            "data": json.dumps({
                "task_id": task_id,
                "status": task.get("status"),
                "progress": task.get("progress", 0),
                "message": task.get("progress_message", "")
            })
        }

        # If task is already in a terminal stream state, close connection.
        if task.get("status") in ["completed", "error", "awaiting_review"]:
            yield {
                "event": "close",
                "data": json.dumps({"status": task.get("status")})
            }
            return

        # Connect to Redis for real-time updates
        redis_client = redis.Redis(
            host=config.redis_host,
            port=config.redis_port,
            decode_responses=True
        )

        try:
            # Subscribe to progress updates
            async for progress_data in ProgressTracker.subscribe_to_progress(redis_client, task_id):
                yield {
                    "event": "progress",
                    "data": json.dumps(progress_data)
                }

                # Close connection if task is done for this stream phase.
                if progress_data.get("status") in ["completed", "error", "awaiting_review"]:
                    yield {
                        "event": "close",
                        "data": json.dumps({"status": progress_data.get("status")})
                    }
                    break

        finally:
            await redis_client.close()

    return EventSourceResponse(event_generator())


@router.patch("/{task_id}")
async def update_task(task_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Update task details (title and review timeline toggle)."""
    headers = request.headers
    user_id = headers.get("user_id")

    if not user_id:
        raise HTTPException(status_code=401, detail="User authentication required")

    try:
        data = await request.json()
        title = data.get("title")
        has_title = isinstance(title, str) and bool(title.strip())
        has_timeline_flag = "timeline_editor_enabled" in data
        if not has_title and not has_timeline_flag:
            raise HTTPException(
                status_code=400,
                detail="At least one of title or timeline_editor_enabled is required",
            )
        timeline_editor_enabled = (
            _resolve_timeline_editor_enabled(data.get("timeline_editor_enabled"))
            if has_timeline_flag
            else None
        )

        task_service = TaskService(db)

        # Get task to verify it exists
        task = await task_service.task_repo.get_task_by_id(db, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        if task["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to update this task")

        if has_title:
            await task_service.source_repo.update_source_title(db, task["source_id"], str(title).strip())
        if timeline_editor_enabled is not None:
            await task_service.task_repo.update_task_timeline_editor_enabled(
                db,
                task_id,
                timeline_editor_enabled,
            )

        return {
            "message": "Task updated successfully",
            "task_id": task_id,
            "timeline_editor_enabled": timeline_editor_enabled if timeline_editor_enabled is not None else task.get("timeline_editor_enabled"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating task: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating task: {str(e)}")


@router.delete("/{task_id}")
async def delete_task(task_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Delete a task and all its associated clips."""
    try:
        headers = request.headers
        user_id = headers.get("user_id")

        if not user_id:
            raise HTTPException(status_code=401, detail="User authentication required")

        task_service = TaskService(db)

        # Get task to verify ownership
        task = await task_service.task_repo.get_task_by_id(db, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        if task["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this task")

        # Delete clips and task
        await task_service.delete_task(task_id)

        return {"message": "Task deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting task: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting task: {str(e)}")


@router.delete("/{task_id}/clips/{clip_id}")
async def delete_clip(task_id: str, clip_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Delete a specific clip."""
    try:
        headers = request.headers
        user_id = headers.get("user_id")

        if not user_id:
            raise HTTPException(status_code=401, detail="User authentication required")

        task_service = TaskService(db)

        # Verify task ownership
        task = await task_service.task_repo.get_task_by_id(db, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        if task["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this clip")

        clip = await task_service.clip_repo.get_clip_by_id(db, clip_id)
        if not clip:
            raise HTTPException(status_code=404, detail="Clip not found")
        if clip["task_id"] != task_id:
            raise HTTPException(status_code=404, detail="Clip not found in this task")

        # Delete the clip
        await task_service.clip_repo.delete_clip(db, clip_id)

        return {"message": "Clip deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting clip: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting clip: {str(e)}")
