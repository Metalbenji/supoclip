from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Any, Dict, Optional, Tuple

from .config import Config

logger = logging.getLogger(__name__)
config = Config()
SUPPORTED_WHISPER_DEVICE_PREFERENCES = ("auto", "cpu", "gpu")


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


def get_local_whisper_runtime_info() -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "supported_device_preferences": list(SUPPORTED_WHISPER_DEVICE_PREFERENCES),
        "cuda_available": False,
        "gpu_count": 0,
        "gpu_devices": [],
        "probe_source": "none",
        "runtime_scope": "current_process",
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
                "probe_source": "torch",
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
                "probe_source": "nvidia-smi",
            }
        )
    except Exception as exc:
        logger.info("nvidia-smi GPU probe unavailable: %s", exc)

    return info


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
