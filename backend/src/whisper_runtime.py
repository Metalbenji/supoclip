from __future__ import annotations

import importlib.util
import logging
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .config import Config

logger = logging.getLogger(__name__)
config = Config()
SUPPORTED_WHISPER_DEVICE_PREFERENCES = ("auto", "cpu", "gpu")
_RUNTIME_LOG_CONTEXTS: set[str] = set()
_RUNTIME_LOG_LOCK = threading.Lock()
_OBSERVED_TRITON_FALLBACK_REASON: Optional[str] = None
LOCAL_WHISPER_MODEL_CATALOG = (
    {
        "value": "turbo",
        "label": "Turbo",
        "speed_hint": "Fastest high-quality",
        "quality_hint": "High quality",
        "approx_vram_hint": "~6 GB VRAM",
        "filename": "large-v3-turbo.pt",
    },
    {
        "value": "medium",
        "label": "Medium",
        "speed_hint": "Balanced",
        "quality_hint": "Balanced quality",
        "approx_vram_hint": "~5 GB VRAM",
        "filename": "medium.pt",
    },
    {
        "value": "large",
        "label": "Large",
        "speed_hint": "Slowest",
        "quality_hint": "Best quality",
        "approx_vram_hint": "~10 GB VRAM",
        "filename": "large-v3.pt",
    },
    {
        "value": "small",
        "label": "Small",
        "speed_hint": "Faster",
        "quality_hint": "Lower quality",
        "approx_vram_hint": "~2 GB VRAM",
        "filename": "small.pt",
    },
    {
        "value": "base",
        "label": "Base",
        "speed_hint": "Lightweight fallback",
        "quality_hint": "Basic quality",
        "approx_vram_hint": "Low VRAM",
        "filename": "base.pt",
    },
    {
        "value": "tiny",
        "label": "Tiny",
        "speed_hint": "Smallest fallback",
        "quality_hint": "Lowest quality",
        "approx_vram_hint": "Low VRAM",
        "filename": "tiny.pt",
    },
)


def _detect_triton_timing_kernel_support() -> Dict[str, Any]:
    triton_installed = importlib.util.find_spec("triton") is not None
    ptxas_path = shutil.which("ptxas")
    enabled = bool(triton_installed and ptxas_path)
    fallback_reason: Optional[str] = None

    if not triton_installed:
        fallback_reason = "Python Triton package is not installed"
    elif not ptxas_path:
        fallback_reason = "CUDA toolkit binary 'ptxas' is not available in the worker image"

    return {
        "triton_package_installed": triton_installed,
        "cuda_toolkit_ptxas_available": bool(ptxas_path),
        "cuda_toolkit_ptxas_path": ptxas_path,
        "triton_timing_kernels_enabled": enabled,
        "triton_fallback_reason": fallback_reason,
        "triton_probe_source": "heuristic",
    }


def _normalize_whisper_device_preference(raw_value: Optional[str]) -> str:
    normalized = (raw_value or "auto").strip().lower()
    if normalized == "cuda":
        return "gpu"
    if normalized not in SUPPORTED_WHISPER_DEVICE_PREFERENCES:
        logger.warning("Unknown Whisper device preference '%s', defaulting to auto", raw_value)
        return "auto"
    return normalized


def _normalize_whisper_gpu_index(raw_value: Any) -> Optional[int]:
    if raw_value is None or raw_value == "":
        return None

    try:
        gpu_index = int(raw_value)
    except (TypeError, ValueError):
        logger.warning("Invalid Whisper GPU index '%s'; ignoring override", raw_value)
        return None

    if gpu_index < 0:
        logger.warning("Negative Whisper GPU index '%s'; ignoring override", raw_value)
        return None
    return gpu_index


def _resolve_whisper_cache_dir() -> Path:
    xdg_cache_home = Path(os.getenv("XDG_CACHE_HOME", "")).expanduser() if os.getenv("XDG_CACHE_HOME") else None
    if xdg_cache_home:
        return xdg_cache_home / "whisper"
    return Path.home() / ".cache" / "whisper"


def get_local_whisper_model_metadata() -> list[dict[str, Any]]:
    cache_dir = _resolve_whisper_cache_dir()
    models: list[dict[str, Any]] = []
    for entry in LOCAL_WHISPER_MODEL_CATALOG:
        filename = str(entry.get("filename") or "").strip()
        cache_status = "cached" if filename and (cache_dir / filename).exists() else "not_cached"
        models.append(
            {
                "value": entry["value"],
                "label": entry["label"],
                "speed_hint": entry["speed_hint"],
                "quality_hint": entry["quality_hint"],
                "approx_vram_hint": entry["approx_vram_hint"],
                "cache_status": cache_status,
            }
        )
    return models


def get_local_whisper_runtime_info() -> Dict[str, Any]:
    triton_support = _detect_triton_timing_kernel_support()
    info: Dict[str, Any] = {
        "supported_device_preferences": list(SUPPORTED_WHISPER_DEVICE_PREFERENCES),
        "cuda_available": False,
        "gpu_count": 0,
        "gpu_devices": [],
        "gpu_device_name": None,
        "probe_source": "none",
        "runtime_scope": "current_process",
        "cache_dir": str(_resolve_whisper_cache_dir()),
        "triton_package_installed": bool(triton_support["triton_package_installed"]),
        "cuda_toolkit_ptxas_available": bool(triton_support["cuda_toolkit_ptxas_available"]),
        "cuda_toolkit_ptxas_path": triton_support["cuda_toolkit_ptxas_path"],
        "triton_timing_kernels_enabled": False,
        "triton_fallback_reason": "CUDA runtime unavailable",
        "triton_probe_source": triton_support["triton_probe_source"],
    }

    try:
        import torch  # type: ignore

        cuda_available = bool(torch.cuda.is_available())
        gpu_devices = []
        device_count = int(torch.cuda.device_count()) if cuda_available else 0
        for gpu_index in range(device_count):
            device_name = str(torch.cuda.get_device_name(gpu_index))
            total_memory_bytes: Optional[int] = None
            try:
                props = torch.cuda.get_device_properties(gpu_index)
                total_memory_bytes = int(getattr(props, "total_memory", 0) or 0)
            except Exception:
                total_memory_bytes = None
            gpu_devices.append(
                {
                    "index": gpu_index,
                    "name": device_name,
                    "total_memory_bytes": total_memory_bytes,
                }
            )

        info.update(
            {
                "cuda_available": cuda_available,
                "gpu_count": device_count,
                "gpu_devices": gpu_devices,
                "gpu_device_name": gpu_devices[0]["name"] if gpu_devices else None,
                "probe_source": "torch",
            }
        )
        if cuda_available:
            info.update(
                {
                    "triton_timing_kernels_enabled": bool(triton_support["triton_timing_kernels_enabled"]),
                    "triton_fallback_reason": triton_support["triton_fallback_reason"],
                }
            )
        with _RUNTIME_LOG_LOCK:
            observed_reason = _OBSERVED_TRITON_FALLBACK_REASON
        if observed_reason:
            info.update(
                {
                    "triton_timing_kernels_enabled": False,
                    "triton_fallback_reason": observed_reason,
                    "triton_probe_source": "observed_warning",
                }
            )
        return info
    except Exception as exc:
        logger.info("Torch CUDA runtime probe unavailable: %s", exc)

    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return info

    try:
        result = subprocess.run(
            [
                nvidia_smi,
                "--query-gpu=index,name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        gpu_devices = []
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            index_text, name, memory_total_mib = [part.strip() for part in line.split(",", 2)]
            total_memory_bytes: Optional[int] = None
            try:
                total_memory_bytes = int(memory_total_mib) * 1024 * 1024
            except (TypeError, ValueError):
                total_memory_bytes = None
            gpu_devices.append(
                {
                    "index": int(index_text),
                    "name": name,
                    "total_memory_bytes": total_memory_bytes,
                }
            )

        info.update(
            {
                "cuda_available": bool(gpu_devices),
                "gpu_count": len(gpu_devices),
                "gpu_devices": gpu_devices,
                "gpu_device_name": gpu_devices[0]["name"] if gpu_devices else None,
                "probe_source": "nvidia-smi",
            }
        )
    except Exception as exc:
        logger.info("nvidia-smi GPU probe unavailable: %s", exc)

    if info["cuda_available"]:
        info.update(
            {
                "triton_timing_kernels_enabled": bool(triton_support["triton_timing_kernels_enabled"]),
                "triton_fallback_reason": triton_support["triton_fallback_reason"],
            }
        )
    with _RUNTIME_LOG_LOCK:
        observed_reason = _OBSERVED_TRITON_FALLBACK_REASON
    if observed_reason:
        info.update(
            {
                "triton_timing_kernels_enabled": False,
                "triton_fallback_reason": observed_reason,
                "triton_probe_source": "observed_warning",
            }
        )
    return info


def record_whisper_triton_fallback(reason: Optional[str]) -> None:
    normalized_reason = (reason or "").strip() or "Whisper Triton timing kernels fell back to the slower CUDA path"
    should_log = False
    with _RUNTIME_LOG_LOCK:
        global _OBSERVED_TRITON_FALLBACK_REASON
        if _OBSERVED_TRITON_FALLBACK_REASON != normalized_reason:
            _OBSERVED_TRITON_FALLBACK_REASON = normalized_reason
            should_log = True
    if should_log:
        logger.warning(
            "Local Whisper GPU runtime is active, but Triton timing kernels are unavailable. "
            "Using slower fallback kernels instead. reason=%s",
            normalized_reason,
        )


def log_local_whisper_runtime_summary(context: str = "runtime") -> None:
    normalized_context = (context or "runtime").strip().lower()
    with _RUNTIME_LOG_LOCK:
        if normalized_context in _RUNTIME_LOG_CONTEXTS:
            return
        _RUNTIME_LOG_CONTEXTS.add(normalized_context)

    info = get_local_whisper_runtime_info()
    logger.info(
        "Local Whisper runtime (%s): cuda_available=%s gpu_device=%s triton_timing_kernels_enabled=%s "
        "triton_fallback_reason=%s",
        normalized_context,
        info.get("cuda_available"),
        info.get("gpu_device_name"),
        info.get("triton_timing_kernels_enabled"),
        info.get("triton_fallback_reason"),
    )


def resolve_whisper_device(
    device_preference_override: Optional[str] = None,
    gpu_index_override: Optional[int] = None,
) -> Tuple[str, bool]:
    desired = _normalize_whisper_device_preference(
        device_preference_override or getattr(config, "whisper_device", "auto")
    )
    preferred_gpu_index = _normalize_whisper_gpu_index(
        gpu_index_override if gpu_index_override is not None else getattr(config, "whisper_gpu_index", None)
    )
    runtime_info = get_local_whisper_runtime_info()
    cuda_available = bool(runtime_info.get("cuda_available"))
    available_gpu_indexes = [
        int(device.get("index"))
        for device in runtime_info.get("gpu_devices", [])
        if isinstance(device, dict) and isinstance(device.get("index"), int)
    ]

    resolved_gpu_index: Optional[int] = None
    if available_gpu_indexes:
        if preferred_gpu_index is None:
            resolved_gpu_index = available_gpu_indexes[0]
        elif preferred_gpu_index in available_gpu_indexes:
            resolved_gpu_index = preferred_gpu_index
        else:
            resolved_gpu_index = available_gpu_indexes[0]
            logger.warning(
                "Requested Whisper GPU index %s is not available; using GPU %s instead",
                preferred_gpu_index,
                resolved_gpu_index,
            )

    if desired == "cpu":
        return "cpu", False

    if desired == "gpu":
        if cuda_available:
            return (
                f"cuda:{resolved_gpu_index}" if resolved_gpu_index is not None else "cuda",
                True,
            )
        logger.warning("Whisper GPU mode requested but no GPU is available; falling back to CPU")
        return "cpu", False

    if cuda_available:
        return (
            f"cuda:{resolved_gpu_index}" if resolved_gpu_index is not None else "cuda",
            True,
        )
    return "cpu", False
