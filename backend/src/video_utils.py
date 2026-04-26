"""
Utility functions for video-related operations.
Optimized for MoviePy v2, local transcription, and high-quality output.
"""

from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Union, Callable
import os
import logging
import gc
from datetime import datetime
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import hashlib
import threading
import urllib.request
import subprocess
import tempfile
import time
import warnings
from difflib import SequenceMatcher
import re

import cv2

if Path("/usr/bin/ffmpeg").exists():
    os.environ.setdefault("IMAGEIO_FFMPEG_EXE", "/usr/bin/ffmpeg")

from moviepy import VideoFileClip, CompositeVideoClip, TextClip, ColorClip

try:
    import assemblyai as aai
except ImportError:  # pragma: no cover - optional provider
    aai = None
import srt
from datetime import timedelta

from .config import Config
from .subtitle_style import normalize_subtitle_style
from .whisper_runtime import (
    get_local_whisper_runtime_info,
    log_local_whisper_runtime_summary,
    record_whisper_triton_fallback,
    resolve_whisper_device,
)

logger = logging.getLogger(__name__)
config = Config()
_whisper_model_cache: Dict[str, Any] = {}
_whisper_model_lock = threading.Lock()
_face_model_path_lock = threading.Lock()
_face_model_path_cache: Optional[Path] = None
_mediapipe_detector_tls = threading.local()
SUPPORTED_FRAMING_MODE_OVERRIDES = ("auto", "prefer_face", "fixed_position")
SUPPORTED_FACE_DETECTION_MODES = ("balanced", "more_faces")
SUPPORTED_FALLBACK_CROP_POSITIONS = ("center", "left_center", "right_center")
SUPPORTED_OUTPUT_ASPECT_RATIOS = ("auto", "1:1", "21:9", "16:9", "9:16", "4:3", "4:5", "5:4", "3:4", "3:2", "2:3")
OUTPUT_ASPECT_RATIO_VALUES: Dict[str, float] = {
    "1:1": 1.0,
    "21:9": 21 / 9,
    "16:9": 16 / 9,
    "9:16": 9 / 16,
    "4:3": 4 / 3,
    "4:5": 4 / 5,
    "5:4": 5 / 4,
    "3:4": 3 / 4,
    "3:2": 3 / 2,
    "2:3": 2 / 3,
}
SUPPORTED_FACE_ANCHOR_PROFILES = (
    "auto",
    "left_only",
    "left_or_center",
    "center_only",
    "right_or_center",
    "right_only",
)
FRAMING_SCORE_BONUS_HIGH = 0.06
FRAMING_SCORE_BONUS_MEDIUM = 0.03
FRAMING_MULTI_FACE_PENALTY_MAX = 0.02
_ffmpeg_encoder_cache: Optional[set[str]] = None
_ffmpeg_encoder_lock = threading.Lock()
_FFMPEG_CORRUPT_AUDIO_MARKERS = (
    "invalid data found when processing input",
    "error submitting packet to decoder",
    "channel element",
    "decode_pce",
    "reserved bit set",
    "prediction is not allowed in aac-lc",
    "number of bands",
    "invalid band type",
    "decoding error",
)


def _normalize_face_detection_mode(value: Any) -> str:
    normalized = str(value or "balanced").strip().lower()
    if normalized == "center_only":
        return "balanced"
    if normalized not in SUPPORTED_FACE_DETECTION_MODES:
        return "balanced"
    return normalized


def _normalize_fallback_crop_position(value: Any) -> str:
    normalized = str(value or "center").strip().lower()
    if normalized not in SUPPORTED_FALLBACK_CROP_POSITIONS:
        return "center"
    return normalized


def _normalize_face_anchor_profile(value: Any) -> str:
    normalized = str(value or "auto").strip().lower()
    if normalized not in SUPPORTED_FACE_ANCHOR_PROFILES:
        return "auto"
    return normalized


def _normalize_output_aspect_ratio(value: Any) -> str:
    normalized = str(value or "9:16").strip().lower()
    if normalized not in SUPPORTED_OUTPUT_ASPECT_RATIOS:
        return "9:16"
    return normalized


def _resolve_target_aspect_ratio(
    original_width: int,
    original_height: int,
    *,
    output_aspect_ratio: str = "9:16",
    target_ratio: Optional[float] = None,
) -> float:
    if target_ratio is not None:
        try:
            resolved = float(target_ratio)
            if resolved > 0:
                return resolved
        except (TypeError, ValueError):
            pass

    normalized_ratio = _normalize_output_aspect_ratio(output_aspect_ratio)
    if normalized_ratio == "auto":
        safe_height = max(1, int(original_height or 1))
        safe_width = max(1, int(original_width or 1))
        return safe_width / safe_height
    return float(OUTPUT_ASPECT_RATIO_VALUES.get(normalized_ratio) or (9 / 16))


def _list_available_ffmpeg_encoders() -> set[str]:
    global _ffmpeg_encoder_cache

    with _ffmpeg_encoder_lock:
        if _ffmpeg_encoder_cache is not None:
            return set(_ffmpeg_encoder_cache)

        try:
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                check=True,
                capture_output=True,
                text=True,
            )
            encoders: set[str] = set()
            for raw_line in result.stdout.splitlines():
                parts = raw_line.strip().split()
                if len(parts) >= 2 and parts[0].startswith("V"):
                    encoders.add(parts[1].strip())
            _ffmpeg_encoder_cache = encoders
        except Exception as exc:
            logger.warning("Failed to probe ffmpeg encoders: %s", exc)
            _ffmpeg_encoder_cache = set()

        return set(_ffmpeg_encoder_cache)


def _ffmpeg_supports_encoder(name: str) -> bool:
    return name in _list_available_ffmpeg_encoders()


def _increment_count(counter: Dict[str, int], key: str) -> None:
    counter[key] = int(counter.get(key) or 0) + 1

class VideoProcessor:
    """Handles video processing operations with optimized settings."""

    def __init__(self, font_family: str = "THEBOLDFONT-FREEVERSION", font_size: int = 24, font_color: str = "#FFFFFF"):
        self.font_family = font_family
        self.font_size = font_size
        self.font_color = font_color
        self.font_path = str(Path(__file__).parent.parent / "fonts" / f"{font_family}.ttf")
        # Fallback to default font if custom font doesn't exist
        if not Path(self.font_path).exists():
            self.font_path = str(Path(__file__).parent.parent / "fonts" / "THEBOLDFONT-FREEVERSION.ttf")

    def get_optimal_encoding_settings(self, target_quality: str = "high") -> Dict[str, Any]:
        """Get optimal encoding settings for different quality levels."""
        settings = {
            "high": {
                "codec": "libx264",
                "audio_codec": "aac",
                "bitrate": "8000k",
                "audio_bitrate": "256k",
                "preset": "medium",
                "ffmpeg_params": ["-crf", "20", "-pix_fmt", "yuv420p", "-profile:v", "main", "-level", "4.1"]
            },
            "medium": {
                "codec": "libx264",
                "audio_codec": "aac",
                "bitrate": "4000k",
                "audio_bitrate": "192k",
                "preset": "fast",
                "ffmpeg_params": ["-crf", "23", "-pix_fmt", "yuv420p"]
            }
        }
        return settings.get(target_quality, settings["high"])

    def get_clip_render_encoding_candidates(self) -> List[Dict[str, Any]]:
        runtime_info = get_local_whisper_runtime_info()
        candidates: List[Dict[str, Any]] = []

        if bool(runtime_info.get("cuda_available")) and _ffmpeg_supports_encoder("h264_nvenc"):
            candidates.append(
                {
                    "encoder_backend": "h264_nvenc",
                    "encoder_profile": "gpu_fast",
                    "settings": {
                        "codec": "h264_nvenc",
                        "audio_codec": "aac",
                        "bitrate": "6000k",
                        "audio_bitrate": "192k",
                        "preset": "p4",
                        "ffmpeg_params": [
                            "-pix_fmt",
                            "yuv420p",
                            "-profile:v",
                            "main",
                        ],
                    },
                }
            )

        candidates.append(
            {
                "encoder_backend": "libx264",
                "encoder_profile": "cpu_fast",
                "settings": {
                    "codec": "libx264",
                    "audio_codec": "aac",
                    "audio_bitrate": "192k",
                    "preset": "veryfast",
                    "ffmpeg_params": ["-crf", "22", "-pix_fmt", "yuv420p", "-profile:v", "main"],
                },
            }
        )
        return candidates

def _get_transcription_provider(provider_override: Optional[str] = None) -> str:
    provider = (provider_override or config.transcription_provider or "local").strip().lower()
    if provider not in {"local", "assemblyai"}:
        logger.warning(f"Unknown transcription provider '{provider}', falling back to local")
        return "local"
    return provider


def _get_whisper_model(model_name: str, device: str):
    cache_key = f"{model_name}:{device}"
    with _whisper_model_lock:
        cached = _whisper_model_cache.get(cache_key)
        if cached is not None:
            return cached

        import whisper

        logger.info(f"Loading local Whisper model '{model_name}' on device '{device}'")
        loaded_model = whisper.load_model(model_name, device=device)
        _whisper_model_cache[cache_key] = loaded_model
        return loaded_model


def release_local_whisper_model_cache() -> None:
    with _whisper_model_lock:
        cached_models = list(_whisper_model_cache.values())
        _whisper_model_cache.clear()

    if not cached_models:
        return

    for model in cached_models:
        try:
            if hasattr(model, "cpu"):
                model.cpu()
        except Exception:
            pass

    del cached_models
    gc.collect()

    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            logger.info("Released cached local Whisper models and emptied CUDA cache")
    except Exception as exc:
        logger.debug("Failed to empty CUDA cache after releasing Whisper models: %s", exc)


def _compute_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def _download_file(url: str, destination: Path) -> None:
    temp_path = destination.with_suffix(destination.suffix + ".download")
    if temp_path.exists():
        temp_path.unlink()
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "mrglsnips/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response, temp_path.open("wb") as target:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                target.write(chunk)
        os.replace(temp_path, destination)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _resolve_mediapipe_face_model_path() -> Optional[Path]:
    global _face_model_path_cache

    configured_path = Path(config.mediapipe_face_model_path).expanduser()
    expected_sha = (config.mediapipe_face_model_sha256 or "").strip().lower()
    model_url = (config.mediapipe_face_model_url or "").strip()
    auto_download = bool(getattr(config, "mediapipe_face_model_auto_download", True))

    with _face_model_path_lock:
        if _face_model_path_cache and _face_model_path_cache.exists():
            return _face_model_path_cache

        if configured_path.exists():
            if expected_sha:
                actual_sha = _compute_file_sha256(configured_path)
                if actual_sha == expected_sha:
                    _face_model_path_cache = configured_path
                    return configured_path
                logger.warning(
                    "MediaPipe face model checksum mismatch at %s: expected %s, got %s",
                    configured_path,
                    expected_sha,
                    actual_sha,
                )
                if not auto_download:
                    return None
            else:
                _face_model_path_cache = configured_path
                return configured_path
        elif not auto_download:
            logger.info(
                "MediaPipe face model not found at %s and auto-download is disabled",
                configured_path,
            )
            return None

        if not model_url:
            logger.warning("MediaPipe face model URL is empty; cannot auto-download model")
            return None

        try:
            configured_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info("Downloading MediaPipe face model to %s", configured_path)
            _download_file(model_url, configured_path)

            if expected_sha:
                actual_sha = _compute_file_sha256(configured_path)
                if actual_sha != expected_sha:
                    configured_path.unlink(missing_ok=True)
                    raise ValueError(
                        f"Checksum mismatch for downloaded model: expected {expected_sha}, got {actual_sha}"
                    )

            _face_model_path_cache = configured_path
            return configured_path
        except Exception as exc:
            logger.warning(f"Failed to prepare MediaPipe face model: {exc}")
            return None


def _get_thread_mediapipe_face_detector() -> Tuple[Any, Optional[str], Any]:
    cached_ctx = getattr(_mediapipe_detector_tls, "face_detector_ctx", None)
    if cached_ctx is not None:
        return cached_ctx

    mp_face_detection = None
    mp_detection_backend: Optional[str] = None
    mp_module = None

    try:
        import mediapipe as mp

        mp_module = mp
        model_path = _resolve_mediapipe_face_model_path()

        if model_path is not None:
            try:
                from mediapipe.tasks.python import vision
                from mediapipe.tasks.python.core.base_options import BaseOptions

                options = vision.FaceDetectorOptions(
                    base_options=BaseOptions(model_asset_path=str(model_path)),
                    min_detection_confidence=0.5,
                )
                mp_face_detection = vision.FaceDetector.create_from_options(options)
                mp_detection_backend = "tasks"
                logger.info("Using MediaPipe Tasks face detector")
            except Exception as exc:
                logger.warning(f"MediaPipe Tasks face detector failed to initialize: {exc}")

        if mp_face_detection is None and hasattr(mp, "solutions"):
            mp_face_detection = mp.solutions.face_detection.FaceDetection(
                model_selection=0,  # 0 for short-range (better for close faces)
                min_detection_confidence=0.5,
            )
            mp_detection_backend = "solutions"
            logger.info("Using MediaPipe Solutions face detector")
        elif mp_face_detection is None:
            logger.info("MediaPipe legacy solutions API unavailable; falling back to OpenCV")
    except ImportError:
        logger.info("MediaPipe not available, falling back to OpenCV")
    except Exception as exc:
        logger.warning(f"MediaPipe face detector failed to initialize: {exc}")

    detector_ctx = (mp_face_detection, mp_detection_backend, mp_module)
    _mediapipe_detector_tls.face_detector_ctx = detector_ctx
    return detector_ctx


def _probe_video_duration_seconds(video_path: Path) -> Optional[float]:
    try:
        with VideoFileClip(str(video_path)) as clip:
            duration = float(clip.duration or 0.0)
            return duration if duration > 0 else None
    except Exception as exc:
        logger.warning(f"Failed to probe video duration for chunking ({video_path}): {exc}")
        return None


def _build_transcription_chunks(
    duration_seconds: float,
    chunk_duration_seconds: int,
    overlap_seconds: int,
) -> List[Tuple[float, float]]:
    safe_chunk_duration = max(int(chunk_duration_seconds), 60)
    safe_overlap = max(int(overlap_seconds), 0)
    if safe_overlap >= safe_chunk_duration:
        safe_overlap = max(0, safe_chunk_duration - 1)

    ranges: List[Tuple[float, float]] = []
    start = 0.0
    while start < duration_seconds:
        end = min(duration_seconds, start + safe_chunk_duration)
        ranges.append((start, end))
        if end >= duration_seconds:
            break
        start = end - safe_overlap

    return ranges


def _resolve_whisper_chunking_settings(
    chunking_enabled_override: Optional[bool],
    chunk_duration_seconds_override: Optional[int],
    chunk_overlap_seconds_override: Optional[int],
) -> Tuple[bool, int, int]:
    chunking_enabled = (
        bool(chunking_enabled_override)
        if chunking_enabled_override is not None
        else bool(getattr(config, "whisper_chunking_enabled", True))
    )
    chunk_duration_seconds = int(
        chunk_duration_seconds_override
        if chunk_duration_seconds_override is not None
        else (getattr(config, "whisper_chunk_duration_seconds", 1200) or 1200)
    )
    chunk_overlap_seconds = int(
        chunk_overlap_seconds_override
        if chunk_overlap_seconds_override is not None
        else (getattr(config, "whisper_chunk_overlap_seconds", 8) or 8)
    )

    chunk_duration_seconds = max(chunk_duration_seconds, 60)
    chunk_overlap_seconds = max(chunk_overlap_seconds, 0)
    if chunk_overlap_seconds >= chunk_duration_seconds:
        chunk_overlap_seconds = max(0, chunk_duration_seconds - 1)
    return chunking_enabled, chunk_duration_seconds, chunk_overlap_seconds


def _emit_transcription_progress(
    progress_callback: Optional[Callable[[Dict[str, Any]], None]],
    payload: Dict[str, Any],
) -> None:
    if progress_callback is None:
        return
    try:
        progress_callback(payload)
    except Exception as exc:
        logger.warning(f"Failed to emit transcription progress payload: {exc}")


def _stderr_indicates_corrupt_audio(stderr_output: str) -> bool:
    normalized = (stderr_output or "").strip().lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in _FFMPEG_CORRUPT_AUDIO_MARKERS)


def _extract_audio_chunk_for_whisper(
    video_path: Path,
    output_path: Path,
    start_seconds: float,
    end_seconds: float,
) -> None:
    duration_seconds = max(end_seconds - start_seconds, 0.05)
    command_attempts = [
        (
            "default",
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-ss",
                f"{start_seconds:.3f}",
                "-i",
                str(video_path),
                "-t",
                f"{duration_seconds:.3f}",
                "-map",
                "0:a:0?",
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(output_path),
            ],
        ),
        (
            "corrupt-audio-recovery",
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-fflags",
                "+discardcorrupt+genpts",
                "-err_detect",
                "ignore_err",
                "-ss",
                f"{start_seconds:.3f}",
                "-i",
                str(video_path),
                "-t",
                f"{duration_seconds:.3f}",
                "-map",
                "0:a:0?",
                "-vn",
                "-af",
                "aresample=async=1:first_pts=0:min_hard_comp=0.100",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(output_path),
            ],
        ),
    ]
    last_stderr = ""

    for attempt_name, cmd in command_attempts:
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
            )
            if not output_path.is_file() or output_path.stat().st_size <= 0:
                raise RuntimeError("ffmpeg produced no audio output")
            if attempt_name != "default":
                logger.warning(
                    "Recovered audio extraction for %s using tolerant ffmpeg settings",
                    video_path.name,
                )
            if result.stderr and _stderr_indicates_corrupt_audio(result.stderr):
                logger.warning(
                    "ffmpeg reported recoverable audio corruption while extracting %s: %s",
                    video_path.name,
                    result.stderr.strip(),
                )
            return
        except subprocess.CalledProcessError as exc:
            stderr_output = (exc.stderr or exc.stdout or "").strip()
            last_stderr = stderr_output
            output_path.unlink(missing_ok=True)
            logger.warning(
                "ffmpeg audio extraction attempt '%s' failed for %s: %s",
                attempt_name,
                video_path.name,
                stderr_output or str(exc),
            )
            if not _stderr_indicates_corrupt_audio(stderr_output):
                raise RuntimeError(
                    f"ffmpeg audio extraction failed while preparing transcription for {video_path.name}"
                ) from exc
        except Exception:
            output_path.unlink(missing_ok=True)
            raise

    if _stderr_indicates_corrupt_audio(last_stderr):
        raise RuntimeError(
            "Source audio stream is corrupted or partially unreadable (AAC decode failure)."
        )

    raise RuntimeError(
        f"ffmpeg audio extraction failed while preparing transcription for {video_path.name}"
    )


def _run_whisper_transcription(model: Any, media_path: Union[Path, str], use_fp16: bool) -> Dict[str, Any]:
    log_local_whisper_runtime_summary("first_whisper_use")
    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter("always")
        result = model.transcribe(
            str(media_path),
            task="transcribe",
            word_timestamps=True,
            verbose=False,
            fp16=use_fp16,
        )

    for caught in caught_warnings:
        message = str(caught.message)
        if "Failed to launch Triton kernels" in message:
            runtime_info = get_local_whisper_runtime_info()
            record_whisper_triton_fallback(
                str(runtime_info.get("triton_fallback_reason") or message)
            )
            continue
        logger.warning("Whisper runtime warning: %s", message)

    return result


def _format_clip_run_prefix(filename_prefix: Optional[str] = None) -> str:
    normalized_prefix = (filename_prefix or "").strip()
    if normalized_prefix:
        return normalized_prefix
    return datetime.now().strftime("%Y%m%d_%H%M")


def _format_clip_time_token(seconds: float) -> str:
    total_seconds = max(0, int(round(seconds)))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    remainder_seconds = total_seconds % 60
    if hours > 0:
        return f"{hours:02d}{minutes:02d}{remainder_seconds:02d}"
    return f"{minutes:02d}{remainder_seconds:02d}"


def _build_clip_filename(
    *,
    clip_index: int,
    start_seconds: float,
    end_seconds: float,
    filename_prefix: Optional[str] = None,
) -> str:
    run_prefix = _format_clip_run_prefix(filename_prefix)
    start_token = _format_clip_time_token(start_seconds)
    end_token = _format_clip_time_token(end_seconds)
    return f"{run_prefix}_clip_{clip_index:03d}_{start_token}-{end_token}.mp4"


def _extract_words_from_whisper_result(
    result: Dict[str, Any],
    *,
    offset_ms: int = 0,
    min_end_ms: Optional[int] = None,
) -> List[Dict[str, Any]]:
    segments = result.get("segments") or []
    words_data: List[Dict[str, Any]] = []

    for segment in segments:
        segment_words = segment.get("words") or []
        for word in segment_words:
            text = str(word.get("word") or "").strip()
            if not text:
                continue

            start_sec = word.get("start")
            end_sec = word.get("end")
            if start_sec is None or end_sec is None:
                continue

            start_ms = int(float(start_sec) * 1000) + offset_ms
            end_ms = int(float(end_sec) * 1000) + offset_ms
            if end_ms <= start_ms:
                continue
            if min_end_ms is not None and end_ms <= min_end_ms:
                continue

            probability = word.get("probability")
            confidence = float(probability) if probability is not None else 1.0
            words_data.append(
                {
                    "text": text,
                    "start": start_ms,
                    "end": end_ms,
                    "confidence": confidence,
                }
            )

    # Fallback for environments where word-level timings are unavailable.
    if words_data:
        return words_data

    for segment in segments:
        text = str(segment.get("text") or "").strip()
        start_sec = segment.get("start")
        end_sec = segment.get("end")
        if not text or start_sec is None or end_sec is None:
            continue
        start_ms = int(float(start_sec) * 1000) + offset_ms
        end_ms = int(float(end_sec) * 1000) + offset_ms
        if end_ms <= start_ms:
            continue
        if min_end_ms is not None and end_ms <= min_end_ms:
            continue
        words_data.append(
            {
                "text": text,
                "start": start_ms,
                "end": end_ms,
                "confidence": 1.0,
            }
        )

    return words_data


def _dedupe_transcript_words(words: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not words:
        return words

    ordered = sorted(words, key=lambda item: (int(item["start"]), int(item["end"])))
    deduped: List[Dict[str, Any]] = []
    seen_exact: set[Tuple[str, int, int]] = set()

    for word in ordered:
        text = str(word.get("text") or "").strip()
        if not text:
            continue
        start_ms = int(word.get("start") or 0)
        end_ms = int(word.get("end") or 0)
        key = (text, start_ms, end_ms)
        if key in seen_exact:
            continue

        if deduped:
            prev = deduped[-1]
            prev_text = str(prev.get("text") or "").strip()
            prev_start = int(prev.get("start") or 0)
            # Guard against overlap duplicates around chunk boundaries.
            if (
                text == prev_text
                and abs(start_ms - prev_start) <= 300
                and abs(end_ms - int(prev.get("end") or 0)) <= 300
            ):
                continue

        seen_exact.add(key)
        deduped.append(
            {
                "text": text,
                "start": start_ms,
                "end": end_ms,
                "confidence": float(word.get("confidence", 1.0) or 1.0),
            }
        )

    return deduped


def _transcribe_with_local_whisper_chunked(
    video_path: Path,
    model: Any,
    use_fp16: bool,
    chunk_ranges: List[Tuple[float, float]],
    overlap_seconds: int,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    total_chunks = len(chunk_ranges)
    transcription_started_at = time.perf_counter()

    logger.info(
        "Starting chunked local Whisper transcription (%s chunks, overlap=%ss)",
        total_chunks,
        overlap_seconds,
    )
    _emit_transcription_progress(
        progress_callback,
        {
            "mode": "chunked",
            "chunk_total": total_chunks,
            "chunks_completed": 0,
            "overlap_seconds": overlap_seconds,
            "stage_progress": 5,
            "message": f"Starting chunked Whisper transcription ({total_chunks} chunks)",
        },
    )

    all_words: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix=f"{video_path.stem}_whisper_", dir=str(video_path.parent)) as temp_dir:
        temp_dir_path = Path(temp_dir)

        for idx, (start_sec, end_sec) in enumerate(chunk_ranges, start=1):
            chunk_started_at = time.perf_counter()
            logger.info(
                "Whisper chunk %s/%s: %.1fs -> %.1fs",
                idx,
                total_chunks,
                start_sec,
                end_sec,
            )
            chunk_path = temp_dir_path / f"chunk_{idx:04d}.wav"
            _extract_audio_chunk_for_whisper(video_path, chunk_path, start_sec, end_sec)
            chunk_result = _run_whisper_transcription(model, chunk_path, use_fp16)

            chunk_offset_ms = int(start_sec * 1000)
            min_end_ms = None
            if idx > 1 and overlap_seconds > 0:
                min_end_ms = int((start_sec + overlap_seconds) * 1000)

            chunk_words = _extract_words_from_whisper_result(
                chunk_result,
                offset_ms=chunk_offset_ms,
                min_end_ms=min_end_ms,
            )
            all_words.extend(chunk_words)
            chunk_elapsed_seconds = round(time.perf_counter() - chunk_started_at, 2)
            total_elapsed_seconds = round(time.perf_counter() - transcription_started_at, 2)
            completed_chunks = idx
            stage_progress = min(95, max(5, int((completed_chunks / total_chunks) * 95)))
            _emit_transcription_progress(
                progress_callback,
                {
                    "mode": "chunked",
                    "chunk_index": idx,
                    "chunk_total": total_chunks,
                    "chunks_completed": completed_chunks,
                    "chunk_start_seconds": round(start_sec, 2),
                    "chunk_end_seconds": round(end_sec, 2),
                    "chunk_elapsed_seconds": chunk_elapsed_seconds,
                    "total_elapsed_seconds": total_elapsed_seconds,
                    "average_chunk_seconds": round(total_elapsed_seconds / completed_chunks, 2),
                    "overlap_seconds": overlap_seconds,
                    "stage_progress": stage_progress,
                    "message": (
                        f"Whisper chunk {idx}/{total_chunks} processed "
                        f"({chunk_elapsed_seconds:.1f}s)"
                    ),
                },
            )

    deduped_words = _dedupe_transcript_words(all_words)
    if not deduped_words:
        raise Exception("Chunked transcription produced no timestamped words")

    transcript_text = " ".join(word["text"] for word in deduped_words).strip()
    total_elapsed_seconds = round(time.perf_counter() - transcription_started_at, 2)
    logger.info(
        "Chunked Whisper transcription complete: chunks=%s total_seconds=%.2f avg_seconds=%.2f words=%s",
        total_chunks,
        total_elapsed_seconds,
        (total_elapsed_seconds / total_chunks) if total_chunks else 0.0,
        len(deduped_words),
    )
    _emit_transcription_progress(
        progress_callback,
        {
            "mode": "chunked",
            "chunk_total": total_chunks,
            "chunks_completed": total_chunks,
            "total_elapsed_seconds": total_elapsed_seconds,
            "average_chunk_seconds": round(total_elapsed_seconds / total_chunks, 2)
            if total_chunks
            else total_elapsed_seconds,
            "stage_progress": 100,
            "message": (
                "Chunked Whisper transcription complete "
                f"({total_chunks} chunks, {total_elapsed_seconds:.1f}s)"
            ),
        },
    )
    return {"words": deduped_words, "text": transcript_text}


def _transcribe_with_local_whisper(
    video_path: Path,
    chunking_enabled_override: Optional[bool] = None,
    chunk_duration_seconds_override: Optional[int] = None,
    chunk_overlap_seconds_override: Optional[int] = None,
    device_preference_override: Optional[str] = None,
    gpu_index_override: Optional[int] = None,
    model_name_override: Optional[str] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    model_name = (model_name_override or config.whisper_model or "medium").strip().lower()
    device, use_fp16 = resolve_whisper_device(
        device_preference_override=device_preference_override,
        gpu_index_override=gpu_index_override,
    )
    model = _get_whisper_model(model_name, device)
    logger.info(
        f"Starting local Whisper transcription using model '{model_name}' "
        f"on device '{device}' (fp16={use_fp16})"
    )
    chunking_enabled, chunk_duration_seconds, overlap_seconds = _resolve_whisper_chunking_settings(
        chunking_enabled_override,
        chunk_duration_seconds_override,
        chunk_overlap_seconds_override,
    )

    if chunking_enabled:
        video_duration = _probe_video_duration_seconds(video_path)
        if video_duration:
            chunk_ranges = _build_transcription_chunks(
                video_duration,
                chunk_duration_seconds=chunk_duration_seconds,
                overlap_seconds=overlap_seconds,
            )
            if len(chunk_ranges) > 1:
                logger.info(
                    "Local Whisper chunking enabled for %s (duration=%.1fs, chunk=%ss, overlap=%ss)",
                    video_path.name,
                    video_duration,
                    chunk_duration_seconds,
                    overlap_seconds,
                )
                return _transcribe_with_local_whisper_chunked(
                    video_path,
                    model=model,
                    use_fp16=use_fp16,
                    chunk_ranges=chunk_ranges,
                    overlap_seconds=overlap_seconds,
                    progress_callback=progress_callback,
                )

    _emit_transcription_progress(
        progress_callback,
        {
            "mode": "single",
            "chunk_total": 1,
            "chunks_completed": 0,
            "stage_progress": 5,
            "message": "Starting Whisper transcription (single pass)",
        },
    )
    transcription_started_at = time.perf_counter()
    result = _run_whisper_transcription(model, video_path, use_fp16)
    transcript_text = str(result.get("text") or "").strip()
    words_data = _extract_words_from_whisper_result(result)

    if not words_data:
        raise Exception("Transcription produced no timestamped words")

    total_elapsed_seconds = round(time.perf_counter() - transcription_started_at, 2)
    logger.info(
        "Single-pass Whisper transcription complete: total_seconds=%.2f words=%s",
        total_elapsed_seconds,
        len(words_data),
    )
    _emit_transcription_progress(
        progress_callback,
        {
            "mode": "single",
            "chunk_index": 1,
            "chunk_total": 1,
            "chunks_completed": 1,
            "chunk_elapsed_seconds": total_elapsed_seconds,
            "total_elapsed_seconds": total_elapsed_seconds,
            "average_chunk_seconds": total_elapsed_seconds,
            "stage_progress": 100,
            "message": f"Whisper transcription complete ({total_elapsed_seconds:.1f}s)",
        },
    )
    return {"words": words_data, "text": transcript_text}


def _transcribe_with_assemblyai(video_path: Path, api_key: Optional[str] = None) -> Dict[str, Any]:
    if aai is None:
        raise Exception("AssemblyAI provider selected but assemblyai package is not installed")
    resolved_api_key = (api_key or config.assembly_ai_api_key or "").strip()
    if not resolved_api_key:
        raise Exception("AssemblyAI provider selected but no API key is available")

    aai.settings.api_key = resolved_api_key
    transcriber = aai.Transcriber()
    config_obj = aai.TranscriptionConfig(
        speaker_labels=False,
        punctuate=True,
        format_text=True,
        speech_models=["universal-2"],
    )

    logger.info("Starting AssemblyAI transcription")
    transcript = transcriber.transcribe(str(video_path), config=config_obj)
    if transcript.status == aai.TranscriptStatus.error:
        raise Exception(f"Transcription failed: {transcript.error}")

    words_data: List[Dict[str, Any]] = []
    if transcript.words:
        for word in transcript.words:
            if word.start is None or word.end is None:
                continue
            if word.end <= word.start:
                continue
            words_data.append(
                {
                    "text": str(word.text or "").strip(),
                    "start": int(word.start),
                    "end": int(word.end),
                    "confidence": float(getattr(word, "confidence", None) or 1.0),
                }
            )

    if not words_data:
        raise Exception("AssemblyAI transcription produced no timestamped words")

    return {"words": words_data, "text": str(getattr(transcript, "text", "") or "").strip()}


def get_video_transcript(
    video_path: Union[Path, str],
    transcription_provider: Optional[str] = None,
    assembly_api_key: Optional[str] = None,
    whisper_chunking_enabled: Optional[bool] = None,
    whisper_chunk_duration_seconds: Optional[int] = None,
    whisper_chunk_overlap_seconds: Optional[int] = None,
    whisper_device_preference: Optional[str] = None,
    whisper_gpu_index: Optional[int] = None,
    whisper_model_size: Optional[str] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> str:
    """Get transcript using configured provider with word-level timings."""
    video_path = Path(video_path)
    logger.info(f"Getting transcript for: {video_path}")

    provider = _get_transcription_provider(transcription_provider)
    logger.info(f"Transcription provider: {provider}")

    try:
        if provider == "assemblyai":
            transcript_data = _transcribe_with_assemblyai(video_path, assembly_api_key)
        else:
            try:
                transcript_data = _transcribe_with_local_whisper(
                    video_path,
                    chunking_enabled_override=whisper_chunking_enabled,
                    chunk_duration_seconds_override=whisper_chunk_duration_seconds,
                    chunk_overlap_seconds_override=whisper_chunk_overlap_seconds,
                    device_preference_override=whisper_device_preference,
                    gpu_index_override=whisper_gpu_index,
                    model_name_override=whisper_model_size,
                    progress_callback=progress_callback,
                )
            finally:
                release_local_whisper_model_cache()

        cache_transcript_data(video_path, transcript_data)
        formatted_transcript = build_formatted_transcript_from_words(transcript_data["words"])
        formatted_lines = [line for line in formatted_transcript.splitlines() if line.strip()]
        cache_formatted_transcript(video_path, formatted_lines)

        result = "\n".join(formatted_lines)
        logger.info(
            f"Transcript formatted: {len(formatted_lines)} segments, "
            f"{len(transcript_data['words'])} words, {len(result)} chars"
        )
        return result
    except Exception as e:
        logger.error(f"Error in transcription: {e}")
        raise

def cache_transcript_data(video_path: Path, transcript: Union[Dict[str, Any], Any]) -> None:
    """Cache provider-agnostic transcript data for subtitle generation."""
    cache_path = video_path.with_suffix('.transcript_cache.json')

    words_data: List[Dict[str, Any]] = []
    transcript_text = ""

    # New provider-agnostic path (dict-like).
    if isinstance(transcript, dict):
        transcript_text = str(transcript.get("text") or "")
        for word in transcript.get("words") or []:
            text = str(word.get("text") or "").strip()
            start = word.get("start")
            end = word.get("end")
            if not text or start is None or end is None:
                continue
            start_ms = int(start)
            end_ms = int(end)
            if end_ms <= start_ms:
                continue
            words_data.append({
                "text": text,
                "start": start_ms,
                "end": end_ms,
                "confidence": float(word.get("confidence", 1.0) or 1.0),
            })
    else:
        # Backward compatibility path for old AssemblyAI object shape.
        transcript_text = str(getattr(transcript, "text", "") or "")
        transcript_words = getattr(transcript, "words", None) or []
        for word in transcript_words:
            if getattr(word, "start", None) is None or getattr(word, "end", None) is None:
                continue
            if word.end <= word.start:
                continue
            words_data.append({
                "text": str(getattr(word, "text", "")).strip(),
                "start": int(word.start),
                "end": int(word.end),
                "confidence": float(getattr(word, "confidence", 1.0) or 1.0),
            })

    cache_data = {"words": words_data, "text": transcript_text}

    with open(cache_path, 'w') as f:
        json.dump(cache_data, f)

    logger.info(f"Cached {len(words_data)} words to {cache_path}")

def cache_formatted_transcript(video_path: Path, formatted_lines: List[str]) -> None:
    """Cache formatted transcript text used by AI analysis."""
    transcript_path = video_path.with_suffix('.transcript.txt')
    transcript_text = '\n'.join(formatted_lines)
    with open(transcript_path, 'w', encoding='utf-8') as f:
        f.write(transcript_text)
    logger.info(f"Cached formatted transcript to {transcript_path}")

def load_cached_transcript_data(video_path: Path) -> Optional[Dict]:
    """Load cached transcript data with word timings."""
    cache_path = video_path.with_suffix('.transcript_cache.json')

    if not cache_path.exists():
        return None

    try:
        with open(cache_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load transcript cache: {e}")
        return None

def build_formatted_transcript_from_words(words: List[Dict[str, Any]]) -> str:
    """Build AI-analysis transcript text from cached word-level timings."""
    if not words:
        return ""

    formatted_lines = []
    current_segment: List[str] = []
    current_start: Optional[int] = None
    segment_word_count = 0
    max_words_per_segment = 8

    for word in words:
        word_text = str(word.get('text', '')).strip()
        if not word_text:
            continue

        word_start = word.get('start')
        word_end = word.get('end')
        if word_start is None or word_end is None:
            continue

        if current_start is None:
            current_start = int(word_start)

        current_segment.append(word_text)
        segment_word_count += 1

        if (
            segment_word_count >= max_words_per_segment
            or word_text.endswith('.')
            or word_text.endswith('!')
            or word_text.endswith('?')
        ):
            start_time = format_ms_to_timestamp(current_start)
            end_time = format_ms_to_timestamp(int(word_end), round_up=True)
            text = ' '.join(current_segment)
            formatted_lines.append(f"[{start_time} - {end_time}] {text}")
            current_segment = []
            current_start = None
            segment_word_count = 0

    if current_segment and current_start is not None:
        last_word_end = int(words[-1].get('end') or current_start)
        start_time = format_ms_to_timestamp(current_start)
        end_time = format_ms_to_timestamp(last_word_end, round_up=True)
        text = ' '.join(current_segment)
        formatted_lines.append(f"[{start_time} - {end_time}] {text}")

    return '\n'.join(formatted_lines)

def get_cached_formatted_transcript(video_path: Union[Path, str]) -> Optional[str]:
    """Load cached formatted transcript text for AI analysis if available."""
    video_path = Path(video_path)
    transcript_path = video_path.with_suffix('.transcript.txt')

    if transcript_path.exists():
        try:
            content = transcript_path.read_text(encoding='utf-8').strip()
            if content:
                return content
        except Exception as e:
            logger.warning(f"Failed to read cached formatted transcript: {e}")

    cached_data = load_cached_transcript_data(video_path)
    if not cached_data:
        return None

    words = cached_data.get('words') or []
    rebuilt = build_formatted_transcript_from_words(words).strip()
    if rebuilt:
        try:
            transcript_path.write_text(rebuilt, encoding='utf-8')
        except Exception as e:
            logger.warning(f"Failed to persist rebuilt transcript cache: {e}")
        return rebuilt

    return None

def format_ms_to_timestamp(ms: int, *, round_up: bool = False) -> str:
    """Format milliseconds to MM:SS format.

    `round_up=True` is used for transcript end boundaries so clip windows do not
    truncate spoken words near the boundary.
    """
    milliseconds = max(0, int(ms))
    if round_up:
        seconds = (milliseconds + 999) // 1000
    else:
        seconds = milliseconds // 1000
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes:02d}:{seconds:02d}"

def round_to_even(value: int) -> int:
    """Round integer to nearest even number for H.264 compatibility."""
    return value - (value % 2)

def _get_target_crop_dimensions(
    original_width: int,
    original_height: int,
    target_ratio: Optional[float] = None,
    output_aspect_ratio: str = "9:16",
) -> Tuple[int, int]:
    resolved_target_ratio = _resolve_target_aspect_ratio(
        original_width,
        original_height,
        output_aspect_ratio=output_aspect_ratio,
        target_ratio=target_ratio,
    )
    original_ratio = original_width / max(1, original_height)

    if abs(original_ratio - resolved_target_ratio) < 1e-4:
        return round_to_even(original_width), round_to_even(original_height)

    if original_ratio > resolved_target_ratio:
        new_width = round_to_even(int(original_height * resolved_target_ratio))
        new_height = round_to_even(original_height)
    else:
        new_width = round_to_even(original_width)
        new_height = round_to_even(int(original_width / resolved_target_ratio))
    return new_width, new_height


def _get_default_center_crop_offsets(
    original_width: int,
    original_height: int,
    crop_width: int,
    crop_height: int,
) -> Tuple[int, int]:
    x_offset = (original_width - crop_width) // 2 if original_width > crop_width else 0
    y_offset = (original_height - crop_height) // 2 if original_height > crop_height else 0
    return round_to_even(x_offset), round_to_even(y_offset)


def _get_fallback_crop_offsets(
    original_width: int,
    original_height: int,
    crop_width: int,
    crop_height: int,
    fallback_crop_position: str = "center",
) -> Tuple[int, int]:
    normalized_position = _normalize_fallback_crop_position(fallback_crop_position)
    max_x = max(0, original_width - crop_width)
    y_offset = (original_height - crop_height) // 2 if original_height > crop_height else 0
    if max_x <= 0:
        return round_to_even(0), round_to_even(y_offset)

    if normalized_position == "left_center":
        x_offset = int(round(max_x * 0.25))
    elif normalized_position == "right_center":
        x_offset = int(round(max_x * 0.75))
    else:
        x_offset = max_x // 2
    return round_to_even(max(0, min(x_offset, max_x))), round_to_even(y_offset)


def _get_face_detection_sample_times(start_time: float, end_time: float) -> List[float]:
    duration = max(0.0, end_time - start_time)
    if duration <= 0:
        return []

    sample_interval = min(0.5, max(duration / 10, 0.2))
    sample_times: List[float] = []
    current_time = start_time
    while current_time < end_time:
        sample_times.append(round(current_time, 4))
        current_time += sample_interval

    middle_time = round(start_time + (duration / 2), 4)
    end_probe_time = round(max(start_time, end_time - min(0.1, duration / 10 if duration > 0 else 0.1)), 4)
    sample_times.extend([middle_time, end_probe_time])

    unique_times = sorted({timestamp for timestamp in sample_times if start_time <= timestamp <= end_time})
    return unique_times


def _collect_face_detection_samples(
    video_clip: VideoFileClip,
    start_time: float,
    end_time: float,
    face_detection_mode: str = "balanced",
) -> List[Dict[str, Any]]:
    samples: List[Dict[str, Any]] = []
    normalized_face_detection_mode = _normalize_face_detection_mode(face_detection_mode)

    try:
        mp_face_detection, mp_detection_backend, mp_module = _get_thread_mediapipe_face_detector()
        haar_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

        dnn_net = None
        try:
            cv2_data_dir = Path(cv2.data.haarcascades)
            prototxt_path = cv2_data_dir / "opencv_face_detector.pbtxt"
            model_path = cv2_data_dir / "opencv_face_detector_uint8.pb"
            if prototxt_path.exists() and model_path.exists():
                dnn_net = cv2.dnn.readNetFromTensorflow(str(model_path), str(prototxt_path))
        except Exception as exc:
            logger.info(f"OpenCV DNN face detector failed to load: {exc}")

        sample_times = _get_face_detection_sample_times(start_time, end_time)
        logger.info("Sampling %s frames for face detection", len(sample_times))

        for sample_time in sample_times:
            try:
                frame = video_clip.get_frame(sample_time)
                height, width = frame.shape[:2]
                detected_faces: List[Tuple[int, int, int, int, float]] = []
                detector_backend = "none"

                if mp_face_detection is not None:
                    try:
                        if mp_detection_backend == "tasks":
                            mp_image = mp_module.Image(
                                image_format=mp_module.ImageFormat.SRGB,
                                data=frame,
                            )
                            result = mp_face_detection.detect(mp_image)
                            for detection in (result.detections or []):
                                bbox = detection.bounding_box
                                x = int(max(0, bbox.origin_x))
                                y = int(max(0, bbox.origin_y))
                                w = int(max(0, bbox.width))
                                h = int(max(0, bbox.height))
                                if x >= width or y >= height:
                                    continue
                                w = min(w, width - x)
                                h = min(h, height - y)
                                if w <= 0 or h <= 0:
                                    continue
                                confidence = 0.5
                                if detection.categories and detection.categories[0].score is not None:
                                    confidence = float(detection.categories[0].score)
                                if w > 30 and h > 30:
                                    detected_faces.append((x, y, w, h, confidence))
                            if detected_faces:
                                detector_backend = "mediapipe_tasks"
                        else:
                            results = mp_face_detection.process(frame)
                            if results.detections:
                                for detection in results.detections:
                                    bbox = detection.location_data.relative_bounding_box
                                    confidence = float(detection.score[0])
                                    x = int(bbox.xmin * width)
                                    y = int(bbox.ymin * height)
                                    w = int(bbox.width * width)
                                    h = int(bbox.height * height)
                                    if w > 30 and h > 30:
                                        detected_faces.append((x, y, w, h, confidence))
                            if detected_faces:
                                detector_backend = "mediapipe_solutions"
                    except Exception as exc:
                        logger.warning("MediaPipe detection failed for frame at %ss: %s", sample_time, exc)

                if not detected_faces and dnn_net is not None:
                    try:
                        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                        blob = cv2.dnn.blobFromImage(frame_bgr, 1.0, (300, 300), [104, 117, 123])
                        dnn_net.setInput(blob)
                        detections = dnn_net.forward()
                        for index in range(detections.shape[2]):
                            confidence = float(detections[0, 0, index, 2])
                            if confidence <= 0.5:
                                continue
                            x1 = int(detections[0, 0, index, 3] * width)
                            y1 = int(detections[0, 0, index, 4] * height)
                            x2 = int(detections[0, 0, index, 5] * width)
                            y2 = int(detections[0, 0, index, 6] * height)
                            w = x2 - x1
                            h = y2 - y1
                            if w > 30 and h > 30:
                                detected_faces.append((x1, y1, w, h, confidence))
                        if detected_faces:
                            detector_backend = "opencv_dnn"
                    except Exception as exc:
                        logger.warning("DNN detection failed for frame at %ss: %s", sample_time, exc)

                if not detected_faces:
                    try:
                        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
                        faces = haar_cascade.detectMultiScale(
                            gray,
                            scaleFactor=1.05,
                            minNeighbors=3,
                            minSize=(40, 40),
                            maxSize=(int(width * 0.7), int(height * 0.7)),
                        )
                        for (x, y, w, h) in faces:
                            face_area = w * h
                            relative_size = face_area / (width * height)
                            confidence = min(0.9, 0.3 + relative_size * 2)
                            detected_faces.append((x, y, w, h, confidence))
                        if detected_faces:
                            detector_backend = "haar"
                    except Exception as exc:
                        logger.warning("Haar cascade detection failed for frame at %ss: %s", sample_time, exc)

                frame_area = max(1, width * height)
                qualified_faces: List[Dict[str, Any]] = []
                rejected_reason_counts = {
                    "too_small": 0,
                    "too_large": 0,
                    "low_confidence": 0,
                    "off_frame": 0,
                }
                min_area_ratio = 0.0035
                min_confidence = 0.2
                max_area_ratio = 0.35
                if normalized_face_detection_mode == "more_faces":
                    min_area_ratio = 0.0015
                    min_confidence = 0.1
                    max_area_ratio = 0.45

                for (x, y, w, h, confidence) in detected_faces:
                    face_area = max(0, w * h)
                    relative_area = face_area / frame_area
                    if x < 0 or y < 0 or (x + w) > width or (y + h) > height:
                        rejected_reason_counts["off_frame"] += 1
                        continue
                    if relative_area <= min_area_ratio:
                        rejected_reason_counts["too_small"] += 1
                        continue
                    if relative_area >= max_area_ratio:
                        rejected_reason_counts["too_large"] += 1
                        continue
                    if float(confidence) < min_confidence:
                        rejected_reason_counts["low_confidence"] += 1
                        continue
                    face_center_x = x + w // 2
                    face_center_y = y + h // 2
                    qualified_faces.append(
                        {
                            "x": int(x),
                            "y": int(y),
                            "width": int(w),
                            "height": int(h),
                            "center_x": int(face_center_x),
                            "center_y": int(face_center_y),
                            "area": int(face_area),
                            "area_ratio": float(relative_area),
                            "confidence": float(confidence),
                        }
                    )

                primary_face = None
                if qualified_faces:
                    primary_face = max(
                        qualified_faces,
                        key=lambda face: float(face["area"]) * float(face["confidence"]),
                    )

                samples.append(
                    {
                        "time": float(sample_time),
                        "frame_width": int(width),
                        "frame_height": int(height),
                        "detector_backend": detector_backend,
                        "raw_face_count": len(detected_faces),
                        "rejected_reason_counts": rejected_reason_counts,
                        "faces": qualified_faces,
                        "primary_face": primary_face,
                    }
                )
            except Exception as exc:
                logger.warning("Error detecting faces in frame at %ss: %s", sample_time, exc)
                continue
    except Exception as exc:
        logger.error("Error collecting face detection samples: %s", exc)

    return samples


def _calculate_weighted_crop_offsets(
    face_centers: List[Tuple[int, int, int, float]],
    original_width: int,
    original_height: int,
    crop_width: int,
    crop_height: int,
) -> Tuple[int, int]:
    if not face_centers:
        return _get_default_center_crop_offsets(original_width, original_height, crop_width, crop_height)

    total_weight = sum(area * confidence for _, _, area, confidence in face_centers)
    if total_weight <= 0:
        return _get_default_center_crop_offsets(original_width, original_height, crop_width, crop_height)

    weighted_x = sum(x * area * confidence for x, _, area, confidence in face_centers) / total_weight
    weighted_y = sum(y * area * confidence for _, y, area, confidence in face_centers) / total_weight
    weighted_y = max(0.0, weighted_y - crop_height * 0.1)

    x_offset = max(0, min(int(weighted_x - crop_width // 2), original_width - crop_width))
    y_offset = max(0, min(int(weighted_y - crop_height // 2), original_height - crop_height))
    return round_to_even(x_offset), round_to_even(y_offset)


def _calculate_face_tracking_offset(
    center_x: int,
    center_y: int,
    frame_width: int,
    frame_height: int,
    crop_width: int,
    crop_height: int,
) -> Tuple[int, int]:
    target_y = max(0.0, float(center_y) - crop_height * 0.1)
    tracked_x = max(0, min(int(float(center_x) - crop_width / 2), frame_width - crop_width))
    tracked_y = max(0, min(int(target_y - crop_height / 2), frame_height - crop_height))
    return round_to_even(tracked_x), round_to_even(tracked_y)


def _get_face_anchor_target_offsets(face_anchor_profile: str, max_x: int) -> List[int]:
    normalized_profile = _normalize_face_anchor_profile(face_anchor_profile)
    center_target = round_to_even(max_x / 2) if max_x > 0 else 0
    if normalized_profile == "left_only":
        return [0]
    if normalized_profile == "left_or_center":
        return [0, center_target]
    if normalized_profile == "center_only":
        return [center_target]
    if normalized_profile == "right_or_center":
        return [center_target, round_to_even(max_x)]
    if normalized_profile == "right_only":
        return [round_to_even(max_x)]
    return []


def _compute_face_anchor_alignment(
    x_offset: float,
    target_offsets: List[int],
    max_x: int,
    crop_width: int,
) -> float:
    if not target_offsets:
        return 0.0
    tolerance = max(90.0, crop_width * 0.35, max_x * 0.18 if max_x > 0 else 0.0)
    min_distance = min(abs(float(target) - float(x_offset)) for target in target_offsets)
    return max(0.0, 1.0 - (min_distance / max(1.0, tolerance)))


def _calculate_face_visibility_score(face_box: Dict[str, Any], frame_width: int, frame_height: int) -> float:
    x = int(face_box.get("x") or 0)
    y = int(face_box.get("y") or 0)
    width = max(0, int(face_box.get("width") or 0))
    height = max(0, int(face_box.get("height") or 0))
    if width <= 0 or height <= 0 or frame_width <= 0 or frame_height <= 0:
        return 0.0

    left_margin = x
    right_margin = max(0, frame_width - (x + width))
    top_margin = y
    bottom_margin = max(0, frame_height - (y + height))
    min_horizontal_margin = min(left_margin, right_margin)
    min_vertical_margin = min(top_margin, bottom_margin)

    horizontal_score = min(1.0, max(0.0, min_horizontal_margin / max(12.0, width * 0.12)))
    vertical_score = min(1.0, max(0.0, min_vertical_margin / max(12.0, height * 0.12)))
    return round((horizontal_score * 0.7) + (vertical_score * 0.3), 4)


def _select_dominant_face_track(
    candidate_points: List[Dict[str, Any]],
    frame_width: int,
    frame_height: int,
    crop_width: int,
    crop_height: int,
    face_anchor_profile: str = "auto",
) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    if not candidate_points:
        return [], {
            "consistency_rate": 0.0,
            "rejected_rate": 0.0,
            "x_spread": 0.0,
            "y_spread": 0.0,
            "anchor_alignment_score": 0.0,
            "anchor_presence_rate": 0.0,
            "visibility_score": 0.0,
        }

    enriched_points: List[Dict[str, Any]] = []
    max_x = max(0, frame_width - crop_width)
    anchor_targets = _get_face_anchor_target_offsets(face_anchor_profile, max_x)
    for point in candidate_points:
        x_offset, y_offset = _calculate_face_tracking_offset(
            int(point.get("center_x") or 0),
            int(point.get("center_y") or 0),
            frame_width,
            frame_height,
            crop_width,
            crop_height,
        )
        enriched_points.append(
            {
                **point,
                "x_offset": x_offset,
                "y_offset": y_offset,
                "anchor_alignment": _compute_face_anchor_alignment(
                    x_offset,
                    anchor_targets,
                    max_x,
                    crop_width,
                ),
                "visibility_score": _calculate_face_visibility_score(point, frame_width, frame_height),
            }
        )

    if len(enriched_points) < 3:
        return enriched_points, {
            "consistency_rate": 1.0,
            "rejected_rate": 0.0,
            "x_spread": 0.0,
            "y_spread": 0.0,
            "anchor_alignment_score": round(
                float(np.mean([float(point.get("anchor_alignment") or 0.0) for point in enriched_points]))
                if enriched_points
                else 0.0,
                4,
            ),
            "anchor_presence_rate": round(
                float(
                    np.mean(
                        [
                            1.0 if float(point.get("anchor_alignment") or 0.0) >= 0.6 else 0.0
                            for point in enriched_points
                        ]
                    )
                )
                if enriched_points
                else 0.0,
                4,
            ),
            "visibility_score": round(
                float(np.mean([float(point.get("visibility_score") or 0.0) for point in enriched_points]))
                if enriched_points
                else 0.0,
                4,
            ),
        }

    cluster_window_x = max(80, round_to_even(int(crop_width * 0.22)))
    cluster_window_y = max(40, round_to_even(int(crop_height * 0.12)))
    best_cluster: List[Dict[str, Any]] = []
    best_score = (-1.0, -1.0, -1.0, 1.0)

    for seed in enriched_points:
        cluster = [
            point
            for point in enriched_points
            if abs(int(point["x_offset"]) - int(seed["x_offset"])) <= cluster_window_x
            and abs(int(point["y_offset"]) - int(seed["y_offset"])) <= cluster_window_y
        ]
        weight_total = sum(float(point.get("area") or 0) * max(0.1, float(point.get("confidence") or 0.0)) for point in cluster)
        mean_offset = (
            sum(float(point["x_offset"]) for point in cluster) / len(cluster)
            if cluster
            else float(seed["x_offset"])
        )
        anchor_alignment = (
            float(np.mean([float(point.get("anchor_alignment") or 0.0) for point in cluster]))
            if cluster
            else 0.0
        )
        score = (
            round(len(cluster) + (anchor_alignment * 0.75), 4),
            anchor_alignment,
            weight_total,
            -abs(float(seed["x_offset"]) - mean_offset),
        )
        if score > best_score:
            best_score = score
            best_cluster = cluster

    if not best_cluster:
        return enriched_points, {
            "consistency_rate": 1.0,
            "rejected_rate": 0.0,
            "x_spread": 0.0,
            "y_spread": 0.0,
        }

    median_x = float(np.median([point["x_offset"] for point in best_cluster]))
    median_y = float(np.median([point["y_offset"] for point in best_cluster]))
    refined_cluster = [
        point
        for point in enriched_points
        if abs(float(point["x_offset"]) - median_x) <= cluster_window_x
        and abs(float(point["y_offset"]) - median_y) <= cluster_window_y
    ]
    if len(refined_cluster) >= max(2, int(len(enriched_points) * 0.35)):
        best_cluster = refined_cluster

    best_cluster = sorted(best_cluster, key=lambda point: float(point.get("time") or 0.0))
    x_positions = [int(point["x_offset"]) for point in best_cluster]
    y_positions = [int(point["y_offset"]) for point in best_cluster]

    return best_cluster, {
        "consistency_rate": round(len(best_cluster) / len(enriched_points), 4),
        "rejected_rate": round(max(0.0, 1.0 - (len(best_cluster) / len(enriched_points))), 4),
        "x_spread": float(max(x_positions) - min(x_positions)) if len(x_positions) > 1 else 0.0,
        "y_spread": float(max(y_positions) - min(y_positions)) if len(y_positions) > 1 else 0.0,
        "anchor_alignment_score": round(
            float(np.mean([float(point.get("anchor_alignment") or 0.0) for point in best_cluster])),
            4,
        ),
        "anchor_presence_rate": round(
            float(
                np.mean(
                    [
                        1.0 if float(point.get("anchor_alignment") or 0.0) >= 0.6 else 0.0
                        for point in best_cluster
                    ]
                )
            ),
            4,
        ),
        "visibility_score": round(
            float(np.mean([float(point.get("visibility_score") or 0.0) for point in best_cluster])),
            4,
        ),
    }


def _calculate_weighted_tracking_offsets(
    tracking_points: List[Dict[str, Any]],
    original_width: int,
    original_height: int,
    crop_width: int,
    crop_height: int,
) -> Tuple[int, int]:
    if not tracking_points:
        return _get_default_center_crop_offsets(original_width, original_height, crop_width, crop_height)

    total_weight = sum(float(point.get("area") or 0) * max(0.1, float(point.get("confidence") or 0.0)) for point in tracking_points)
    if total_weight <= 0:
        x_values = [int(point.get("x_offset") or 0) for point in tracking_points]
        y_values = [int(point.get("y_offset") or 0) for point in tracking_points]
        return (
            round_to_even(int(np.median(x_values))) if x_values else 0,
            round_to_even(int(np.median(y_values))) if y_values else 0,
        )

    weighted_x = sum(float(point.get("x_offset") or 0) * float(point.get("area") or 0) * max(0.1, float(point.get("confidence") or 0.0)) for point in tracking_points) / total_weight
    weighted_y = sum(float(point.get("y_offset") or 0) * float(point.get("area") or 0) * max(0.1, float(point.get("confidence") or 0.0)) for point in tracking_points) / total_weight
    max_x = max(0, original_width - crop_width)
    max_y = max(0, original_height - crop_height)
    return (
        round_to_even(max(0, min(int(weighted_x), max_x))),
        round_to_even(max(0, min(int(weighted_y), max_y))),
    )


def _summarize_face_detection_samples(
    samples: List[Dict[str, Any]],
    start_time: float,
    crop_width: int,
    crop_height: int,
    face_detection_mode: str = "balanced",
    fallback_crop_position: str = "center",
    face_anchor_profile: str = "auto",
) -> Dict[str, Any]:
    normalized_face_detection_mode = _normalize_face_detection_mode(face_detection_mode)
    normalized_fallback_crop_position = _normalize_fallback_crop_position(fallback_crop_position)
    normalized_face_anchor_profile = _normalize_face_anchor_profile(face_anchor_profile)
    if not samples:
        return {
            "face_detected": False,
            "face_detection_rate": 0.0,
            "primary_face_area_ratio": None,
            "dominant_face_count": 0,
            "multi_face_frames_rate": 0.0,
            "crop_confidence": "none",
            "suggested_crop_mode": "center",
            "score_adjustment": 0.0,
            "sampled_frames": 0,
            "raw_face_frames": 0,
            "reliable_face_frames": 0,
            "detector_backend": "none",
            "detection_state": "none",
            "filter_reason_counts": {
                "too_small": 0,
                "too_large": 0,
                "low_confidence": 0,
                "off_frame": 0,
            },
            "face_detection_mode": normalized_face_detection_mode,
            "fallback_crop_position": normalized_fallback_crop_position,
            "face_anchor_profile": normalized_face_anchor_profile,
            "face_centers": [],
            "tracking_points": [],
        }

    sample_count = len(samples)
    primary_area_ratios: List[float] = []
    face_counts: List[int] = []
    face_centers: List[Tuple[int, int, int, float]] = []
    tracking_points: List[Dict[str, Any]] = []
    candidate_tracking_points: List[Dict[str, Any]] = []
    raw_face_frames = 0
    reliable_face_frames = 0
    multi_face_frames = 0
    detector_backend_counts: Dict[str, int] = {}
    filter_reason_counts = {
        "too_small": 0,
        "too_large": 0,
        "low_confidence": 0,
        "off_frame": 0,
    }

    for sample in samples:
        backend_name = str(sample.get("detector_backend") or "none")
        if backend_name != "none":
            detector_backend_counts[backend_name] = detector_backend_counts.get(backend_name, 0) + 1

        for key in filter_reason_counts:
            filter_reason_counts[key] += int((sample.get("rejected_reason_counts") or {}).get(key) or 0)

        if int(sample.get("raw_face_count") or 0) > 0:
            raw_face_frames += 1

        faces = list(sample.get("faces") or [])
        if not faces:
            continue

        face_count = len(faces)
        primary_face = sample.get("primary_face") or faces[0]
        candidate_tracking_points.append(
            {
                "time": round(float(sample.get("time") or 0.0) - start_time, 4),
                "center_x": int(primary_face.get("center_x") or 0),
                "center_y": int(primary_face.get("center_y") or 0),
                "x": int(primary_face.get("x") or 0),
                "y": int(primary_face.get("y") or 0),
                "width": int(primary_face.get("width") or 0),
                "height": int(primary_face.get("height") or 0),
                "area": int(primary_face.get("area") or 0),
                "area_ratio": float(primary_face.get("area_ratio") or 0.0),
                "confidence": float(primary_face.get("confidence") or 0.0),
                "face_count": face_count,
                "detector_backend": backend_name,
            }
        )

    frame_width = int(samples[0].get("frame_width") or 0)
    frame_height = int(samples[0].get("frame_height") or 0)
    dominant_track_points, tracking_metrics = _select_dominant_face_track(
        candidate_tracking_points,
        frame_width,
        frame_height,
        crop_width,
        crop_height,
        face_anchor_profile=normalized_face_anchor_profile,
    )

    for point in dominant_track_points:
        reliable_face_frames += 1
        face_count = int(point.get("face_count") or 0)
        face_counts.append(face_count)
        if face_count > 1:
            multi_face_frames += 1

        area_ratio = float(point.get("area_ratio") or 0.0)
        primary_area_ratios.append(area_ratio)
        face_centers.append(
            (
                int(point.get("center_x") or 0),
                int(point.get("center_y") or 0),
                int(point.get("area") or 0),
                float(point.get("confidence") or 0.0),
            )
        )
        tracking_points.append(
            {
                "time": round(float(point.get("time") or 0.0), 4),
                "x_offset": int(point.get("x_offset") or 0),
                "y_offset": int(point.get("y_offset") or 0),
                "face_count": face_count,
                "confidence": float(point.get("confidence") or 0.0),
            }
        )

    if len(face_centers) > 2:
        face_centers = filter_face_outliers(face_centers)

    face_detection_rate = round(raw_face_frames / sample_count, 4) if sample_count > 0 else 0.0
    reliable_face_rate = round(reliable_face_frames / sample_count, 4) if sample_count > 0 else 0.0
    multi_face_frames_rate = round(multi_face_frames / sample_count, 4) if sample_count > 0 else 0.0
    primary_face_area_ratio = round(float(np.mean(primary_area_ratios)), 4) if primary_area_ratios else None
    detector_backend = "none"
    if detector_backend_counts:
        detector_backend = max(
            detector_backend_counts.items(),
            key=lambda item: (item[1], item[0]),
        )[0]

    dominant_face_count = 0
    if face_counts:
        unique_counts, count_totals = np.unique(np.array(face_counts), return_counts=True)
        dominant_face_count = int(unique_counts[int(np.argmax(count_totals))])

    crop_confidence = "none"
    anchor_alignment_score = float(tracking_metrics.get("anchor_alignment_score") or 0.0)
    anchor_presence_rate = float(tracking_metrics.get("anchor_presence_rate") or 0.0)
    visibility_score = float(tracking_metrics.get("visibility_score") or 0.0)
    anchored_layout_expected = normalized_face_anchor_profile != "auto"
    if reliable_face_frames > 0:
        crop_confidence = "low"
        auto_high = (
            dominant_face_count == 1
            and reliable_face_rate >= 0.6
            and (primary_face_area_ratio or 0.0) >= 0.02
            and multi_face_frames_rate <= 0.15
            and tracking_metrics.get("consistency_rate", 0.0) >= 0.7
            and tracking_metrics.get("x_spread", 0.0) <= max(120.0, crop_width * 0.22)
        )
        anchored_high = (
            anchored_layout_expected
            and dominant_face_count == 1
            and reliable_face_rate >= 0.45
            and (primary_face_area_ratio or 0.0) >= 0.008
            and multi_face_frames_rate <= 0.45
            and tracking_metrics.get("consistency_rate", 0.0) >= 0.45
            and anchor_alignment_score >= 0.72
            and anchor_presence_rate >= 0.65
            and visibility_score >= 0.45
            and tracking_metrics.get("x_spread", 0.0) <= max(160.0, crop_width * 0.3)
        )
        if auto_high or anchored_high:
            crop_confidence = "high"
        else:
            auto_medium = (
                dominant_face_count == 1
                and reliable_face_rate >= 0.35
                and (primary_face_area_ratio or 0.0) >= (0.008 if normalized_face_detection_mode == "more_faces" else 0.01)
                and multi_face_frames_rate <= 0.35
                and tracking_metrics.get("consistency_rate", 0.0) >= 0.5
                and tracking_metrics.get("x_spread", 0.0) <= max(180.0, crop_width * 0.32)
            )
            anchored_medium = (
                anchored_layout_expected
                and dominant_face_count == 1
                and reliable_face_rate >= 0.28
                and (primary_face_area_ratio or 0.0) >= 0.0045
                and multi_face_frames_rate <= 0.6
                and tracking_metrics.get("consistency_rate", 0.0) >= 0.32
                and anchor_alignment_score >= 0.58
                and anchor_presence_rate >= 0.5
                and visibility_score >= 0.3
                and tracking_metrics.get("x_spread", 0.0) <= max(240.0, crop_width * 0.4)
            )
            if auto_medium or anchored_medium:
                crop_confidence = "medium"

    if (
        anchored_layout_expected
        and crop_confidence == "low"
        and reliable_face_frames > 0
        and dominant_face_count == 1
        and anchor_presence_rate >= 0.45
        and visibility_score >= 0.25
    ):
        crop_confidence = "medium"

    if (
        detector_backend == "haar"
        and tracking_metrics.get("consistency_rate", 0.0) < 0.65
        and anchor_presence_rate < 0.6
    ):
        crop_confidence = "low" if reliable_face_frames > 0 else "none"
    elif (
        detector_backend == "haar"
        and anchored_layout_expected
        and anchor_presence_rate >= 0.65
        and visibility_score >= 0.45
        and crop_confidence == "low"
    ):
        crop_confidence = "medium"

    suggested_crop_mode = "face" if crop_confidence in {"high", "medium"} else "center"
    detection_state = "none"
    if crop_confidence in {"high", "medium"}:
        detection_state = "strong"
    elif raw_face_frames > 0:
        detection_state = "weak"

    score_adjustment = 0.0
    if dominant_face_count == 1 and reliable_face_rate >= 0.35:
        if crop_confidence == "high":
            score_adjustment += FRAMING_SCORE_BONUS_HIGH
        elif crop_confidence == "medium":
            score_adjustment += FRAMING_SCORE_BONUS_MEDIUM
    if reliable_face_frames > 0 and multi_face_frames_rate > 0.25:
        score_adjustment -= min(FRAMING_MULTI_FACE_PENALTY_MAX, round(multi_face_frames_rate * 0.05, 4))

    x_offset, y_offset = _calculate_weighted_tracking_offsets(
        dominant_track_points,
        frame_width,
        frame_height,
        crop_width,
        crop_height,
    )

    return {
        "face_detected": bool(raw_face_frames > 0),
        "face_detection_rate": face_detection_rate,
        "primary_face_area_ratio": primary_face_area_ratio,
        "dominant_face_count": dominant_face_count,
        "multi_face_frames_rate": multi_face_frames_rate,
        "crop_confidence": crop_confidence,
        "suggested_crop_mode": suggested_crop_mode,
        "score_adjustment": round(score_adjustment, 4),
        "sampled_frames": sample_count,
        "raw_face_frames": raw_face_frames,
        "reliable_face_frames": reliable_face_frames,
        "detector_backend": detector_backend,
        "detection_state": detection_state,
        "filter_reason_counts": filter_reason_counts,
        "face_detection_mode": normalized_face_detection_mode,
        "fallback_crop_position": normalized_fallback_crop_position,
        "face_anchor_profile": normalized_face_anchor_profile,
        "face_centers": face_centers,
        "tracking_points": tracking_points,
        "tracking_consistency_rate": round(float(tracking_metrics.get("consistency_rate") or 0.0), 4),
        "tracking_rejected_rate": round(float(tracking_metrics.get("rejected_rate") or 0.0), 4),
        "tracking_x_spread": round(float(tracking_metrics.get("x_spread") or 0.0), 2),
        "tracking_y_spread": round(float(tracking_metrics.get("y_spread") or 0.0), 2),
        "tracking_anchor_alignment_score": round(anchor_alignment_score, 4),
        "tracking_anchor_presence_rate": round(anchor_presence_rate, 4),
        "tracking_visibility_score": round(visibility_score, 4),
        "fixed_crop_offsets": (x_offset, y_offset),
    }


def _smooth_numeric_series(values: np.ndarray, window_size: int = 3) -> np.ndarray:
    if values.size <= 2 or window_size <= 1:
        return values
    kernel = np.ones(window_size) / window_size
    padded = np.pad(values, (window_size // 2, window_size // 2), mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def _build_tracked_crop_clip(
    clip: VideoFileClip,
    crop_width: int,
    crop_height: int,
    tracking_points: List[Dict[str, Any]],
    fallback_offsets: Tuple[int, int],
) -> VideoFileClip:
    if not tracking_points:
        x_offset, y_offset = fallback_offsets
        return clip.cropped(
            x1=x_offset,
            y1=y_offset,
            x2=x_offset + crop_width,
            y2=y_offset + crop_height,
        )

    sorted_points = sorted(tracking_points, key=lambda point: float(point.get("time") or 0.0))
    duration = max(0.0, float(clip.duration or 0.0))

    times = np.array([max(0.0, float(point.get("time") or 0.0)) for point in sorted_points], dtype=float)
    x_offsets = np.array([float(point.get("x_offset") or 0.0) for point in sorted_points], dtype=float)
    y_offsets = np.array([float(point.get("y_offset") or 0.0) for point in sorted_points], dtype=float)

    if times.size == 0:
        return clip.cropped(
            x1=fallback_offsets[0],
            y1=fallback_offsets[1],
            x2=fallback_offsets[0] + crop_width,
            y2=fallback_offsets[1] + crop_height,
        )

    if times[0] > 0.0:
        times = np.insert(times, 0, 0.0)
        x_offsets = np.insert(x_offsets, 0, x_offsets[0])
        y_offsets = np.insert(y_offsets, 0, y_offsets[0])
    if duration > 0.0 and times[-1] < duration:
        times = np.append(times, duration)
        x_offsets = np.append(x_offsets, x_offsets[-1])
        y_offsets = np.append(y_offsets, y_offsets[-1])

    x_offsets = _smooth_numeric_series(x_offsets)
    y_offsets = _smooth_numeric_series(y_offsets)
    max_x = max(0, int(clip.w - crop_width))
    max_y = max(0, int(clip.h - crop_height))

    def crop_frame(get_frame: Callable[[float], np.ndarray], timestamp: float) -> np.ndarray:
        frame = get_frame(timestamp)
        interpolated_x = int(np.interp(timestamp, times, x_offsets))
        interpolated_y = int(np.interp(timestamp, times, y_offsets))
        x_offset = max(0, min(round_to_even(interpolated_x), max_x))
        y_offset = max(0, min(round_to_even(interpolated_y), max_y))
        return frame[y_offset:y_offset + crop_height, x_offset:x_offset + crop_width]

    return clip.transform(crop_frame)


def analyze_clip_framing(
    video_clip: VideoFileClip,
    start_time: float,
    end_time: float,
    target_ratio: Optional[float] = None,
    face_detection_mode: str = "balanced",
    fallback_crop_position: str = "center",
    face_anchor_profile: str = "auto",
    output_aspect_ratio: str = "9:16",
) -> Dict[str, Any]:
    original_width, original_height = video_clip.size
    normalized_output_aspect_ratio = _normalize_output_aspect_ratio(output_aspect_ratio)
    resolved_target_ratio = _resolve_target_aspect_ratio(
        original_width,
        original_height,
        output_aspect_ratio=normalized_output_aspect_ratio,
        target_ratio=target_ratio,
    )
    crop_width, crop_height = _get_target_crop_dimensions(
        original_width,
        original_height,
        target_ratio=resolved_target_ratio,
        output_aspect_ratio=normalized_output_aspect_ratio,
    )
    normalized_face_detection_mode = _normalize_face_detection_mode(face_detection_mode)
    normalized_fallback_crop_position = _normalize_fallback_crop_position(fallback_crop_position)
    normalized_face_anchor_profile = _normalize_face_anchor_profile(face_anchor_profile)
    samples = _collect_face_detection_samples(
        video_clip,
        start_time,
        end_time,
        face_detection_mode=normalized_face_detection_mode,
    )
    summary = _summarize_face_detection_samples(
        samples,
        start_time,
        crop_width,
        crop_height,
        face_detection_mode=normalized_face_detection_mode,
        fallback_crop_position=normalized_fallback_crop_position,
        face_anchor_profile=normalized_face_anchor_profile,
    )
    fallback_offsets = _get_fallback_crop_offsets(
        original_width,
        original_height,
        crop_width,
        crop_height,
        normalized_fallback_crop_position,
    )
    fixed_crop_offsets = summary.get("fixed_crop_offsets") or fallback_offsets

    framing_metadata = {
        "face_detected": bool(summary.get("face_detected")),
        "face_detection_rate": float(summary.get("face_detection_rate") or 0.0),
        "primary_face_area_ratio": summary.get("primary_face_area_ratio"),
        "dominant_face_count": int(summary.get("dominant_face_count") or 0),
        "multi_face_frames_rate": float(summary.get("multi_face_frames_rate") or 0.0),
        "crop_confidence": str(summary.get("crop_confidence") or "none"),
        "suggested_crop_mode": str(summary.get("suggested_crop_mode") or "center"),
        "score_adjustment": float(summary.get("score_adjustment") or 0.0),
        "sampled_frames": int(summary.get("sampled_frames") or 0),
        "raw_face_frames": int(summary.get("raw_face_frames") or 0),
        "reliable_face_frames": int(summary.get("reliable_face_frames") or 0),
        "detector_backend": str(summary.get("detector_backend") or "none"),
        "detection_state": str(summary.get("detection_state") or "none"),
        "filter_reason_counts": dict(summary.get("filter_reason_counts") or {}),
        "face_detection_mode": str(summary.get("face_detection_mode") or normalized_face_detection_mode),
        "fallback_crop_position": str(summary.get("fallback_crop_position") or normalized_fallback_crop_position),
        "face_anchor_profile": str(summary.get("face_anchor_profile") or normalized_face_anchor_profile),
        "output_aspect_ratio": normalized_output_aspect_ratio,
        "target_aspect_ratio": float(resolved_target_ratio),
        "tracking_consistency_rate": float(summary.get("tracking_consistency_rate") or 0.0),
        "tracking_rejected_rate": float(summary.get("tracking_rejected_rate") or 0.0),
        "tracking_x_spread": float(summary.get("tracking_x_spread") or 0.0),
        "tracking_y_spread": float(summary.get("tracking_y_spread") or 0.0),
        "tracking_anchor_alignment_score": float(summary.get("tracking_anchor_alignment_score") or 0.0),
        "tracking_anchor_presence_rate": float(summary.get("tracking_anchor_presence_rate") or 0.0),
        "tracking_visibility_score": float(summary.get("tracking_visibility_score") or 0.0),
    }
    return {
        "framing_metadata": framing_metadata,
        "crop_width": crop_width,
        "crop_height": crop_height,
        "fixed_crop_offsets": fixed_crop_offsets,
        "tracking_points": list(summary.get("tracking_points") or []),
        "face_centers": list(summary.get("face_centers") or []),
    }


def analyze_single_segment_framing(
    video_path: Union[Path, str],
    start_time: str,
    end_time: str,
    face_detection_mode: str = "balanced",
    fallback_crop_position: str = "center",
    face_anchor_profile: str = "auto",
    output_aspect_ratio: str = "9:16",
) -> Dict[str, Any]:
    start_seconds = parse_timestamp_to_seconds(start_time)
    end_seconds = parse_timestamp_to_seconds(end_time)
    if end_seconds <= start_seconds:
        return {}
    with VideoFileClip(str(video_path)) as video:
        analysis = analyze_clip_framing(
            video,
            start_seconds,
            end_seconds,
            face_detection_mode=face_detection_mode,
            fallback_crop_position=fallback_crop_position,
            face_anchor_profile=face_anchor_profile,
            output_aspect_ratio=output_aspect_ratio,
        )
    metadata = dict(analysis.get("framing_metadata") or {})
    metadata["crop_width"] = int(analysis.get("crop_width") or 0)
    metadata["crop_height"] = int(analysis.get("crop_height") or 0)
    metadata["fixed_crop_offsets"] = list(analysis.get("fixed_crop_offsets") or [])
    metadata["tracking_points"] = list(analysis.get("tracking_points") or [])
    return metadata


def analyze_segment_framing_batch(
    video_path: Union[Path, str],
    segments: List[Dict[str, Any]],
    face_detection_mode: str = "balanced",
    fallback_crop_position: str = "center",
    face_anchor_profile: str = "auto",
    output_aspect_ratio: str = "9:16",
) -> List[Dict[str, Any]]:
    video_path = Path(video_path)
    results: List[Dict[str, Any]] = []
    with VideoFileClip(str(video_path)) as video:
        for segment in segments:
            try:
                start_seconds = parse_timestamp_to_seconds(segment.get("start_time", "00:00"))
                end_seconds = parse_timestamp_to_seconds(segment.get("end_time", "00:00"))
                if end_seconds <= start_seconds:
                    results.append({})
                    continue
                analysis = analyze_clip_framing(
                    video,
                    start_seconds,
                    end_seconds,
                    face_detection_mode=face_detection_mode,
                    fallback_crop_position=(
                        segment.get("fallback_crop_position")
                        or fallback_crop_position
                    ),
                    face_anchor_profile=(
                        segment.get("face_anchor_profile")
                        or face_anchor_profile
                    ),
                    output_aspect_ratio=(
                        segment.get("output_aspect_ratio")
                        or output_aspect_ratio
                    ),
                )
                metadata = dict(analysis.get("framing_metadata") or {})
                metadata["crop_width"] = int(analysis.get("crop_width") or 0)
                metadata["crop_height"] = int(analysis.get("crop_height") or 0)
                metadata["fixed_crop_offsets"] = list(analysis.get("fixed_crop_offsets") or [])
                metadata["tracking_points"] = list(analysis.get("tracking_points") or [])
                results.append(metadata)
            except Exception as exc:
                logger.warning(
                    "Failed framing analysis for segment %s -> %s: %s",
                    segment.get("start_time"),
                    segment.get("end_time"),
                    exc,
                )
                results.append({})
    return results


def detect_optimal_crop_region(video_clip: VideoFileClip, start_time: float, end_time: float, target_ratio: float = 9/16) -> Tuple[int, int, int, int]:
    """Detect a fixed crop region using face framing analysis."""
    try:
        analysis = analyze_clip_framing(video_clip, start_time, end_time, target_ratio=target_ratio)
        x_offset, y_offset = analysis.get("fixed_crop_offsets") or (0, 0)
        crop_width = int(analysis.get("crop_width") or video_clip.w)
        crop_height = int(analysis.get("crop_height") or video_clip.h)
        return int(x_offset), int(y_offset), crop_width, crop_height
    except Exception as exc:
        logger.error("Error in crop detection: %s", exc)
        crop_width, crop_height = _get_target_crop_dimensions(video_clip.w, video_clip.h, target_ratio)
        x_offset, y_offset = _get_default_center_crop_offsets(video_clip.w, video_clip.h, crop_width, crop_height)
        return x_offset, y_offset, crop_width, crop_height


def detect_faces_in_clip(video_clip: VideoFileClip, start_time: float, end_time: float) -> List[Tuple[int, int, int, float]]:
    """Return simplified face centers for compatibility with older callers."""
    try:
        crop_width, crop_height = _get_target_crop_dimensions(video_clip.w, video_clip.h, 9 / 16)
        samples = _collect_face_detection_samples(video_clip, start_time, end_time)
        summary = _summarize_face_detection_samples(samples, start_time, crop_width, crop_height)
        face_centers = list(summary.get("face_centers") or [])
        logger.info("Detected %s reliable face centers", len(face_centers))
        return face_centers
    except Exception as exc:
        logger.error("Error in face detection: %s", exc)
        return []

def filter_face_outliers(face_centers: List[Tuple[int, int, int, float]]) -> List[Tuple[int, int, int, float]]:
    """Remove face detections that are outliers (likely false positives)."""
    if len(face_centers) < 3:
        return face_centers

    try:
        # Calculate median position
        x_positions = [x for x, y, area, conf in face_centers]
        y_positions = [y for x, y, area, conf in face_centers]

        median_x = np.median(x_positions)
        median_y = np.median(y_positions)

        # Calculate standard deviation
        std_x = np.std(x_positions)
        std_y = np.std(y_positions)

        # Filter out faces that are more than 2 standard deviations away
        filtered_faces = []
        for face in face_centers:
            x, y, area, conf = face
            if (abs(x - median_x) <= 2 * std_x and abs(y - median_y) <= 2 * std_y):
                filtered_faces.append(face)

        logger.info(f"Filtered {len(face_centers)} -> {len(filtered_faces)} faces (removed outliers)")
        return filtered_faces if filtered_faces else face_centers  # Return original if all filtered

    except Exception as e:
        logger.warning(f"Error filtering face outliers: {e}")
        return face_centers

def parse_timestamp_to_seconds(timestamp_str: str) -> float:
    """Parse timestamp string to seconds."""
    try:
        timestamp_str = timestamp_str.strip()
        logger.info(f"Parsing timestamp: '{timestamp_str}'")  # Debug logging

        if ':' in timestamp_str:
            parts = timestamp_str.split(':')
            if len(parts) == 2:
                minutes = int(parts[0])
                seconds = float(parts[1])
                if seconds < 0 or seconds >= 60:
                    raise ValueError("seconds must be in [0, 60)")
                result = minutes * 60 + seconds
                logger.info(f"Parsed '{timestamp_str}' -> {result}s")
                return result
            elif len(parts) == 3:  # HH:MM:SS format
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = float(parts[2])
                if minutes < 0 or minutes > 59 or seconds < 0 or seconds >= 60:
                    raise ValueError("invalid HH:MM:SS timestamp")
                result = hours * 3600 + minutes * 60 + seconds
                logger.info(f"Parsed '{timestamp_str}' -> {result}s")
                return result

        # Try parsing as pure seconds
        result = float(timestamp_str)
        logger.info(f"Parsed '{timestamp_str}' as seconds -> {result}s")
        return result

    except (ValueError, IndexError) as e:
        logger.error(f"Failed to parse timestamp '{timestamp_str}': {e}")
        return 0.0


_ALIGNMENT_TOKEN_RE = re.compile(r"[A-Za-z0-9']+")


def _tokenize_alignment_text(text: str) -> List[str]:
    return [match.group(0) for match in _ALIGNMENT_TOKEN_RE.finditer(text or "")]


def _normalize_alignment_token(token: str) -> str:
    return re.sub(r"[^a-z0-9']", "", (token or "").strip().lower())


def _extract_clip_words_for_alignment(
    video_path: Path,
    clip_start: float,
    clip_end: float,
) -> List[Dict[str, Any]]:
    clip_duration = max(0.01, float(clip_end) - float(clip_start))
    if clip_duration <= 0:
        raise ValueError("Invalid clip range for subtitle alignment")

    model_name = config.whisper_model or "medium"
    device, use_fp16 = resolve_whisper_device()
    model = _get_whisper_model(model_name, device)

    with tempfile.TemporaryDirectory(prefix=f"{video_path.stem}_align_", dir=str(video_path.parent)) as temp_dir:
        audio_path = Path(temp_dir) / "alignment_clip.wav"
        _extract_audio_chunk_for_whisper(video_path, audio_path, clip_start, clip_end)
        result = _run_whisper_transcription(model, audio_path, use_fp16)
        raw_words = _extract_words_from_whisper_result(result)

    aligned_words: List[Dict[str, Any]] = []
    for word in raw_words:
        text = str(word.get("text") or "").strip()
        if not text:
            continue

        normalized = _normalize_alignment_token(text)
        if not normalized:
            continue

        start_seconds = max(0.0, min(clip_duration, float(word.get("start", 0)) / 1000.0))
        end_seconds = max(0.0, min(clip_duration, float(word.get("end", 0)) / 1000.0))
        if end_seconds <= start_seconds:
            continue

        aligned_words.append(
            {
                "text": text,
                "normalized": normalized,
                "start": start_seconds,
                "end": end_seconds,
            }
        )

    return aligned_words


def align_edited_text_to_clip_audio(
    video_path: Union[Path, str],
    clip_start: float,
    clip_end: float,
    edited_text: str,
) -> List[Dict[str, Any]]:
    """
    Align edited subtitle text to clip audio and return per-word timings relative to clip start.
    """
    video_path = Path(video_path)
    target_tokens = _tokenize_alignment_text(edited_text)
    if not target_tokens:
        raise ValueError("Edited subtitle text is empty after tokenization")

    reference_words = _extract_clip_words_for_alignment(video_path, clip_start, clip_end)
    if not reference_words:
        raise ValueError("Could not derive word timings from clip audio")

    target_normalized = [_normalize_alignment_token(token) for token in target_tokens]
    reference_normalized = [word["normalized"] for word in reference_words]
    clip_duration = max(0.01, float(clip_end) - float(clip_start))

    matcher = SequenceMatcher(a=reference_normalized, b=target_normalized, autojunk=False)
    timings: List[Optional[Dict[str, float]]] = [None] * len(target_tokens)

    for tag, ref_start, ref_end, target_start, target_end in matcher.get_opcodes():
        if tag != "equal":
            continue
        for offset in range(min(ref_end - ref_start, target_end - target_start)):
            ref_word = reference_words[ref_start + offset]
            timings[target_start + offset] = {
                "start": float(ref_word["start"]),
                "end": float(ref_word["end"]),
            }

    # Interpolate timings for unmatched words based on nearest matched anchors.
    index = 0
    while index < len(timings):
        if timings[index] is not None:
            index += 1
            continue

        span_start = index
        while index < len(timings) and timings[index] is None:
            index += 1
        span_end = index - 1
        span_count = span_end - span_start + 1

        left_anchor = timings[span_start - 1]["end"] if span_start > 0 and timings[span_start - 1] else 0.0
        right_anchor = timings[index]["start"] if index < len(timings) and timings[index] else clip_duration

        if right_anchor <= left_anchor:
            right_anchor = min(clip_duration, left_anchor + (0.14 * span_count))
            if right_anchor <= left_anchor:
                right_anchor = left_anchor + (0.08 * span_count)

        step = max(0.05, (right_anchor - left_anchor) / max(1, span_count))
        cursor = left_anchor
        for span_index in range(span_start, span_end + 1):
            start_time = max(0.0, min(clip_duration, cursor))
            end_time = max(start_time + 0.05, min(clip_duration, cursor + step))
            timings[span_index] = {"start": start_time, "end": end_time}
            cursor += step

    # Final monotonic pass so words are strictly ordered and inside clip duration.
    aligned_words: List[Dict[str, Any]] = []
    previous_end = 0.0
    for token, timing in zip(target_tokens, timings):
        if timing is None:
            continue

        start_time = max(previous_end, min(clip_duration, float(timing["start"])))
        end_time = max(start_time + 0.05, min(clip_duration, float(timing["end"])))
        if end_time <= start_time:
            end_time = min(clip_duration, start_time + 0.05)
            if end_time <= start_time:
                start_time = max(0.0, clip_duration - 0.05)
                end_time = clip_duration

        aligned_words.append(
            {
                "text": token,
                "start": round(start_time, 3),
                "end": round(end_time, 3),
            }
        )
        previous_end = end_time

    if not aligned_words:
        raise ValueError("Word-level alignment produced no timings")

    return aligned_words


def _apply_text_transform(text: str, transform: str) -> str:
    if transform == "uppercase":
        return text.upper()
    if transform == "lowercase":
        return text.lower()
    if transform == "capitalize":
        return " ".join(word.capitalize() for word in text.split(" "))
    return text


def _apply_letter_spacing(text: str, spacing: int) -> str:
    if spacing <= 0:
        return text
    joiner = " " * spacing
    spaced_words = []
    for word in text.split(" "):
        if len(word) <= 1:
            spaced_words.append(word)
        else:
            spaced_words.append(joiner.join(list(word)))
    return " ".join(spaced_words)


def _shadow_offsets(base_x: int, base_y: int, blur: int) -> List[Tuple[int, int]]:
    offsets = [(base_x, base_y)]
    if blur <= 0:
        return offsets

    spread = min(3, blur)
    offsets.extend(
        [
            (base_x - spread, base_y),
            (base_x + spread, base_y),
            (base_x, base_y - spread),
            (base_x, base_y + spread),
        ]
    )
    if blur >= 2:
        offsets.extend(
            [
                (base_x - spread, base_y - spread),
                (base_x + spread, base_y - spread),
                (base_x - spread, base_y + spread),
                (base_x + spread, base_y + spread),
            ]
        )
    return offsets


def _resolve_karaoke_highlight_color(base_color: str) -> str:
    normalized = str(base_color or "").strip().upper()
    if normalized in {"#FDE047", "#FACC15", "#FFD700", "#FFE066"}:
        return "#FFFFFF"
    return "#FDE047"


KARAOKE_WORD_HORIZONTAL_PADDING_PX = 12
KARAOKE_WORD_VERTICAL_PADDING_PX = 6
KARAOKE_TIMING_SHIFT_SECONDS = 0.55


def _compute_vertical_effect_padding(
    font_size: int,
    stroke_width: int,
    stroke_blur: float,
    shadow_blur: int,
    shadow_offset_y: int,
) -> Tuple[int, int]:
    """
    Reserve extra text box space so descenders and effect layers are not clipped.

    Returns (top_padding_px, bottom_padding_px).
    """
    # Descenders vary per font; keep a small proportional guard to prevent hard clipping.
    descender_guard = max(2, int(round(font_size * 0.12)))
    stroke_guard = max(0, int(round(stroke_width + (stroke_blur * 1.5))))
    shadow_top_guard = max(0, int(round(shadow_blur - shadow_offset_y)))
    shadow_bottom_guard = max(0, int(round(shadow_blur + shadow_offset_y)))

    top_padding = max(stroke_guard, shadow_top_guard)
    bottom_padding = max(descender_guard, stroke_guard, shadow_bottom_guard)
    return top_padding, bottom_padding


def _measure_label_text(text: str, font_path: str, font_size: int) -> Tuple[int, int]:
    if not text:
        return (0, max(1, int(font_size)))
    try:
        measure_clip = TextClip(
            text=text,
            font=font_path,
            font_size=font_size,
            color="#FFFFFF",
            stroke_width=0,
            method="label",
        )
        try:
            if measure_clip.size:
                return (max(1, int(measure_clip.size[0])), max(1, int(measure_clip.size[1])))
            return (max(1, int(font_size * 0.6 * len(text))), max(1, int(font_size)))
        finally:
            measure_clip.close()
    except Exception:
        return (max(1, int(font_size * 0.6 * len(text))), max(1, int(font_size)))


def _build_styled_word_layers(
    *,
    text: str,
    font_path: str,
    font_size: int,
    fill_color: str,
    stroke_color: str,
    stroke_width: int,
    stroke_blur: float,
    shadow_color: str,
    shadow_opacity: float,
    shadow_blur: int,
    shadow_offset_x: int,
    shadow_offset_y: int,
    font_weight: int,
    start: float,
    duration: float,
    base_x: int,
    base_y: int,
    box_width: int,
    box_height: int,
    max_x: int,
    max_y: int,
    opacity_scale: float = 1.0,
    animated_y_start: Optional[int] = None,
) -> List[TextClip]:
    if not text or duration <= 0 or box_width <= 0 or box_height <= 0:
        return []

    layered_clips: List[TextClip] = []
    safe_opacity_scale = max(0.0, min(1.0, float(opacity_scale)))

    # Build position function — either static or animated (vertical scroll).
    # NOTE: MoviePy v2 calls self.pos(ct) where ct = t - self.start (clip-local
    # time starting at 0). So the lambda receives t=0 when the clip first appears.
    if animated_y_start is not None and duration > 0:
        _y_from = animated_y_start
        _y_to = base_y
        # Ease-out cubic: fast start, gentle deceleration
        _anim_duration = min(0.45, duration * 0.6)

        def _pos_fn(x: int, y: int):
            """Return a MoviePy-compatible position lambda.

            ``t`` here is clip-local time (0 at first frame of the clip).
            """
            return lambda t: (
                x,
                int(_y_from + (_y_to - _y_from) * min(1.0, (t / _anim_duration) ** 0.6))
                if _anim_duration > 0
                else y,
            )

        def _layer_pos(x: int, y: int):
            return _pos_fn(max(0, min(x, max_x)), max(0, min(y, max_y)))
    else:
        def _layer_pos(x: int, y: int):
            return (max(0, min(x, max_x)), max(0, min(y, max_y)))

    def _make_text_clip(
        *,
        color: str,
        stroke_color_value: Optional[str],
        stroke_width_value: int,
    ) -> Optional[TextClip]:
        try:
            return TextClip(
                text=text,
                font=font_path,
                font_size=font_size,
                color=color,
                stroke_color=stroke_color_value,
                stroke_width=stroke_width_value,
                method="caption",
                size=(box_width, box_height),
                text_align="center",
            ).with_start(start).with_duration(duration)
        except Exception:
            try:
                return TextClip(
                    text=text,
                    font=font_path,
                    font_size=font_size,
                    color=color,
                    stroke_color=stroke_color_value,
                    stroke_width=stroke_width_value,
                    method="label",
                ).with_start(start).with_duration(duration)
            except Exception:
                return None

    fill_clip = _make_text_clip(
        color=fill_color,
        stroke_color_value=None,
        stroke_width_value=0,
    )
    if fill_clip is None:
        return []

    rendered_outline_width = max(0, stroke_width * 2)
    soft_stroke_clip: Optional[TextClip] = None
    stroke_text_clip: Optional[TextClip] = None
    soft_stroke_opacity = 0.0

    if rendered_outline_width > 0:
        stroke_text_clip = _make_text_clip(
            color=stroke_color,
            stroke_color_value=stroke_color,
            stroke_width_value=rendered_outline_width,
        )
        if stroke_blur > 0:
            soft_outline_expansion = max(1, int(round(stroke_blur * 2)))
            soft_stroke_clip = _make_text_clip(
                color=stroke_color,
                stroke_color_value=stroke_color,
                stroke_width_value=rendered_outline_width + soft_outline_expansion,
            )
            if soft_stroke_clip is not None:
                soft_stroke_opacity = max(0.18, min(0.7, stroke_blur / 2.5))

    if shadow_opacity > 0:
        shadow_clip = _make_text_clip(
            color=shadow_color,
            stroke_color_value=shadow_color,
            stroke_width_value=0,
        )
        if shadow_clip is not None:
            offsets = _shadow_offsets(shadow_offset_x, shadow_offset_y, shadow_blur)
            per_layer_opacity = max(0.02, min(1.0, shadow_opacity / max(1, len(offsets))))
            for offset_x, offset_y in offsets:
                layer_x = max(0, min(base_x + offset_x, max_x))
                layer_y = max(0, min(base_y + offset_y, max_y))
                layered_clips.append(
                    shadow_clip.with_position(_layer_pos(layer_x, layer_y)).with_opacity(
                        per_layer_opacity * safe_opacity_scale
                    )
                )

    if soft_stroke_clip is not None and soft_stroke_opacity > 0:
        layered_clips.append(
            soft_stroke_clip.with_position(_layer_pos(base_x, base_y)).with_opacity(soft_stroke_opacity * safe_opacity_scale)
        )

    if stroke_text_clip is not None:
        layered_clips.append(
            stroke_text_clip.with_position(_layer_pos(base_x, base_y)).with_opacity(max(0.01, safe_opacity_scale))
        )

    weight_offsets: List[Tuple[int, int]] = []
    if font_weight >= 600:
        weight_offsets.append((1, 0))
    if font_weight >= 800:
        weight_offsets.extend([(0, 1), (-1, 0)])

    for offset_x, offset_y in weight_offsets:
        layer_x = max(0, min(base_x + offset_x, max_x))
        layer_y = max(0, min(base_y + offset_y, max_y))
        layered_clips.append(
            fill_clip.with_position(_layer_pos(layer_x, layer_y)).with_opacity(0.8 * safe_opacity_scale)
        )

    layered_clips.append(fill_clip.with_position(_layer_pos(base_x, base_y)).with_opacity(max(0.01, safe_opacity_scale)))
    return layered_clips


def create_assemblyai_subtitles(
    video_path: Union[Path, str],
    clip_start: float,
    clip_end: float,
    video_width: int,
    video_height: int,
    font_family: str = "THEBOLDFONT-FREEVERSION",
    font_size: int = 24,
    font_color: str = "#FFFFFF",
    subtitle_style: Optional[Dict[str, Any]] = None,
    word_timings_override: Optional[List[Dict[str, Any]]] = None,
) -> List[TextClip]:
    """Create subtitles using cached word timings."""
    video_path = Path(video_path)
    style = normalize_subtitle_style(subtitle_style)
    style["font_family"] = font_family or style["font_family"]
    style["font_size"] = int(font_size or style["font_size"])
    style["font_color"] = font_color or style["font_color"]

    # Convert clip timing to milliseconds
    clip_start_ms = int(clip_start * 1000)
    clip_end_ms = int(clip_end * 1000)
    clip_duration_seconds = max(0.0, clip_end - clip_start)

    relevant_words = []
    if word_timings_override:
        for word_data in word_timings_override:
            text = str(word_data.get("text") or "").strip()
            if not text:
                continue
            start_seconds = float(word_data.get("start") or 0.0)
            end_seconds = float(word_data.get("end") or 0.0)
            start_seconds = max(0.0, min(clip_duration_seconds, start_seconds))
            end_seconds = max(0.0, min(clip_duration_seconds, end_seconds))
            if end_seconds <= start_seconds:
                continue
            relevant_words.append(
                {
                    "text": text,
                    "start": start_seconds,
                    "end": end_seconds,
                    "confidence": float(word_data.get("confidence", 1.0) or 1.0),
                }
            )
    else:
        transcript_data = load_cached_transcript_data(video_path)
        if not transcript_data or not transcript_data.get("words"):
            logger.warning("No cached transcript data available for subtitles")
            return []

        # Find words that fall within our clip timerange
        for word_data in transcript_data["words"]:
            word_start = word_data["start"]
            word_end = word_data["end"]

            # Check if word overlaps with clip
            if word_start < clip_end_ms and word_end > clip_start_ms:
                # Adjust timing relative to clip start
                relative_start = max(0, (word_start - clip_start_ms) / 1000.0)
                relative_end = min((clip_end_ms - clip_start_ms) / 1000.0, (word_end - clip_start_ms) / 1000.0)

                if relative_end > relative_start:
                    relevant_words.append(
                        {
                            "text": word_data["text"],
                            "start": relative_start,
                            "end": relative_end,
                            "confidence": word_data.get("confidence", 1.0),
                        }
                    )

    if not relevant_words:
        logger.warning("No words found in clip timerange")
        return []
    relevant_words.sort(key=lambda word: (float(word.get("start", 0.0)), float(word.get("end", 0.0))))

    if KARAOKE_TIMING_SHIFT_SECONDS > 0:
        shifted_words: List[Dict[str, Any]] = []
        for word in relevant_words:
            shifted_start = max(0.0, min(clip_duration_seconds, float(word["start"]) + KARAOKE_TIMING_SHIFT_SECONDS))
            shifted_end = max(0.0, min(clip_duration_seconds, float(word["end"]) + KARAOKE_TIMING_SHIFT_SECONDS))
            if shifted_end <= shifted_start:
                continue
            shifted_words.append(
                {
                    "text": word["text"],
                    "start": shifted_start,
                    "end": shifted_end,
                    "confidence": float(word.get("confidence", 1.0) or 1.0),
                }
            )
        if shifted_words:
            relevant_words = shifted_words

    # Group words into short subtitle segments for readability, then animate
    # each word by overlaying a timed highlight on top of a persistent base line.
    subtitle_clips: List[TextClip] = []
    processor = VideoProcessor(style["font_family"], style["font_size"], style["font_color"])

    calculated_font_size = max(24, min(48, int(style["font_size"] * (video_width / 640) * 1.15)))
    final_font_size = calculated_font_size
    base_stroke_width = max(0, int(style["stroke_width"]))
    if style["font_size"] > 0:
        stroke_scale = final_font_size / style["font_size"]
        stroke_width = max(0, int(round(base_stroke_width * stroke_scale)))
    else:
        stroke_width = base_stroke_width
    stroke_blur = float(style["stroke_blur"])
    letter_spacing = int(style["letter_spacing"])
    text_transform = str(style["text_transform"])
    text_align = str(style["text_align"])
    shadow_color = str(style["shadow_color"])
    shadow_opacity = float(style["shadow_opacity"])
    shadow_blur = int(style["shadow_blur"])
    shadow_offset_x = int(style["shadow_offset_x"])
    shadow_offset_y = int(style["shadow_offset_y"])
    font_weight = int(style["font_weight"])
    highlight_color = str(style.get("highlight_color") or "").strip()
    if not highlight_color:
        highlight_color = _resolve_karaoke_highlight_color(str(style["font_color"]))
    dim_unhighlighted = bool(style.get("dim_unhighlighted", True))
    subtitle_position = str(style.get("position", "bottom"))
    subtitle_animation = str(style.get("animation", "none"))
    print(f"[SUBTITLE_DEBUG] style resolved: position={subtitle_position} animation={subtitle_animation} keys={list(style.keys())}", flush=True)

    words_per_subtitle = 3
    for i in range(0, len(relevant_words), words_per_subtitle):
        word_group = relevant_words[i:i + words_per_subtitle]
        if not word_group:
            continue

        segment_start = float(word_group[0]["start"])
        segment_end = float(word_group[-1]["end"])
        segment_duration = segment_end - segment_start
        if segment_duration < 0.1:
            continue

        display_words: List[str] = []
        word_timings: List[Tuple[float, float]] = []
        for word in word_group:
            transformed = _apply_text_transform(str(word["text"]), text_transform)
            transformed = _apply_letter_spacing(transformed, letter_spacing)
            if not transformed.strip():
                continue
            word_start = float(word["start"])
            word_end = float(word["end"])
            if word_end <= word_start:
                continue
            display_words.append(transformed)
            word_timings.append((word_start, word_end))

        if not display_words:
            continue

        space_width, _ = _measure_label_text(" ", processor.font_path, final_font_size)
        space_width = max(1, space_width)
        word_sizes = [_measure_label_text(word_text, processor.font_path, final_font_size) for word_text in display_words]
        word_widths = [size[0] for size in word_sizes]
        word_heights = [size[1] for size in word_sizes]
        total_width = sum(word_widths) + (space_width * max(0, len(display_words) - 1))
        text_height = max([final_font_size] + word_heights)
        top_effect_padding, bottom_effect_padding = _compute_vertical_effect_padding(
            final_font_size,
            stroke_width,
            stroke_blur,
            shadow_blur,
            shadow_offset_y,
        )
        line_box_height = (
            text_height
            + (KARAOKE_WORD_VERTICAL_PADDING_PX * 2)
            + top_effect_padding
            + bottom_effect_padding
        )

        horizontal_padding = int(video_width * 0.04)
        if text_align == "left":
            line_start_x = horizontal_padding
        elif text_align == "right":
            line_start_x = video_width - horizontal_padding - total_width
        else:
            line_start_x = (video_width - total_width) // 2
        max_line_start = max(0, video_width - total_width)
        line_start_x = max(0, min(int(line_start_x), max_line_start))

        # Resolve vertical position based on subtitle_position setting.
        if subtitle_position == "top":
            target_y_ratio = 0.15
        elif subtitle_position == "center":
            target_y_ratio = 0.45
        else:
            target_y_ratio = 0.70

        base_y = int(video_height * target_y_ratio - line_box_height // 2)
        max_y = max(0, video_height - line_box_height)
        base_y = max(0, min(base_y, max_y))

        # Vertical scroll: each word group slides down from above.
        animated_y_start = None
        scroll_fade_scale = None
        if subtitle_animation == "vertical_scroll":
            # Start position: ~25% of video height above the target
            animated_y_start = max(0, base_y - int(video_height * 0.25))
            # Apply a gentle fade-in for the first moments
            scroll_fade_scale = 1.0
            logger.info(
                "VERTICAL SCROLL enabled for segment %s: base_y=%s y_start=%s video_h=%s",
                i, base_y, animated_y_start, video_height,
            )
            print(f"[SUBTITLE_DEBUG] VERTICAL SCROLL segment {i}: base_y={base_y} y_start={animated_y_start} video_h={video_height}", flush=True)

        current_x = line_start_x
        for word_index, (word_text, (word_start, word_end), word_width) in enumerate(
            zip(display_words, word_timings, word_widths)
        ):
            word_box_width = max(1, word_width + (KARAOKE_WORD_HORIZONTAL_PADDING_PX * 2))
            word_box_x = current_x - KARAOKE_WORD_HORIZONTAL_PADDING_PX
            word_box_max_x = max(0, video_width - word_box_width)
            word_box_x = max(0, min(word_box_x, word_box_max_x))
            base_layers = _build_styled_word_layers(
                text=word_text,
                font_path=processor.font_path,
                font_size=final_font_size,
                fill_color=str(style["font_color"]),
                stroke_color=str(style["stroke_color"]),
                stroke_width=stroke_width,
                stroke_blur=stroke_blur,
                shadow_color=shadow_color,
                shadow_opacity=shadow_opacity,
                shadow_blur=shadow_blur,
                shadow_offset_x=shadow_offset_x,
                shadow_offset_y=shadow_offset_y,
                font_weight=font_weight,
                start=segment_start,
                duration=segment_duration,
                base_x=word_box_x,
                base_y=base_y,
                box_width=word_box_width,
                box_height=line_box_height,
                max_x=word_box_max_x,
                max_y=max_y,
                opacity_scale=(0.52 if dim_unhighlighted else 1.0) * (scroll_fade_scale if scroll_fade_scale is not None else 1.0),
                animated_y_start=animated_y_start,
            )
            subtitle_clips.extend(base_layers)

            if word_index < len(word_timings) - 1:
                next_word_start = float(word_timings[word_index + 1][0])
                highlight_end = max(word_end, next_word_start)
            else:
                highlight_end = max(word_end, segment_end)
            highlight_duration = max(0.01, highlight_end - word_start)
            highlight_layers = _build_styled_word_layers(
                text=word_text,
                font_path=processor.font_path,
                font_size=final_font_size,
                fill_color=highlight_color,
                stroke_color=str(style["stroke_color"]),
                stroke_width=stroke_width,
                stroke_blur=stroke_blur,
                shadow_color=shadow_color,
                shadow_opacity=shadow_opacity,
                shadow_blur=shadow_blur,
                shadow_offset_x=shadow_offset_x,
                shadow_offset_y=shadow_offset_y,
                font_weight=font_weight,
                start=word_start,
                duration=highlight_duration,
                base_x=word_box_x,
                base_y=base_y,
                box_width=word_box_width,
                box_height=line_box_height,
                max_x=word_box_max_x,
                max_y=max_y,
                opacity_scale=1.0 * (scroll_fade_scale if scroll_fade_scale is not None else 1.0),
                animated_y_start=animated_y_start,
            )
            subtitle_clips.extend(highlight_layers)

            current_x += word_width + space_width

    logger.info(f"Created {len(subtitle_clips)} subtitle elements from cached transcript data")
    return subtitle_clips

def create_optimized_clip(
    video_path: Union[Path, str],
    start_time: float,
    end_time: float,
    output_path: Union[Path, str],
    add_subtitles: bool = True,
    font_family: str = "THEBOLDFONT-FREEVERSION",
    font_size: int = 24,
    font_color: str = "#FFFFFF",
    subtitle_style: Optional[Dict[str, Any]] = None,
    subtitle_word_timings: Optional[List[Dict[str, Any]]] = None,
    framing_mode_override: str = "auto",
    framing_metadata: Optional[Dict[str, Any]] = None,
    output_aspect_ratio: str = "9:16",
    error_collector: Optional[List[str]] = None,
    render_details_sink: Optional[Dict[str, Any]] = None,
) -> bool:
    """Create an optimized clip with word-timed subtitles."""
    try:
        video_path = Path(video_path)
        output_path = Path(output_path)
        duration = end_time - start_time
        if duration <= 0:
            logger.error(f"Invalid clip duration: {duration:.1f}s")
            return False

        logger.info(f"Creating clip: {start_time:.1f}s - {end_time:.1f}s ({duration:.1f}s)")

        # Load and process video
        video = VideoFileClip(str(video_path))

        if start_time >= video.duration:
            logger.error(f"Start time {start_time}s exceeds video duration {video.duration:.1f}s")
            video.close()
            return False

        end_time = min(end_time, video.duration)
        clip = video.subclipped(start_time, end_time)
        framing_mode = str(framing_mode_override or "auto").strip().lower()
        if framing_mode == "disable_face_crop":
            framing_mode = "fixed_position"
        if framing_mode not in SUPPORTED_FRAMING_MODE_OVERRIDES:
            framing_mode = "auto"

        normalized_output_aspect_ratio = _normalize_output_aspect_ratio(output_aspect_ratio)
        new_width, new_height = _get_target_crop_dimensions(
            video.w,
            video.h,
            output_aspect_ratio=normalized_output_aspect_ratio,
        )
        effective_framing_metadata = dict(framing_metadata or {})
        fallback_crop_position = _normalize_fallback_crop_position(
            effective_framing_metadata.get("fallback_crop_position")
        )
        fallback_x_offset, fallback_y_offset = _get_fallback_crop_offsets(
            video.w,
            video.h,
            new_width,
            new_height,
            fallback_crop_position,
        )
        crop_mode = "center"
        crop_reason = "fixed_position_override" if framing_mode == "fixed_position" else "no_reliable_face"
        crop_confidence = str(effective_framing_metadata.get("crop_confidence") or "none")
        detection_state = str(effective_framing_metadata.get("detection_state") or "none")
        face_detection_mode = _normalize_face_detection_mode(effective_framing_metadata.get("face_detection_mode"))
        face_anchor_profile = _normalize_face_anchor_profile(effective_framing_metadata.get("face_anchor_profile"))
        framing_analysis_source = "persisted_metadata"
        tracking_points = list(effective_framing_metadata.get("tracking_points") or [])
        persisted_crop_width = int(effective_framing_metadata.get("crop_width") or 0)
        persisted_crop_height = int(effective_framing_metadata.get("crop_height") or 0)
        persisted_fixed_offsets_raw = effective_framing_metadata.get("fixed_crop_offsets")
        persisted_fixed_offsets: Optional[Tuple[int, int]] = None
        if isinstance(persisted_fixed_offsets_raw, (list, tuple)) and len(persisted_fixed_offsets_raw) == 2:
            try:
                persisted_fixed_offsets = (
                    int(persisted_fixed_offsets_raw[0]),
                    int(persisted_fixed_offsets_raw[1]),
                )
            except (TypeError, ValueError):
                persisted_fixed_offsets = None

        if framing_mode == "fixed_position":
            cropped_clip = clip.cropped(
                x1=fallback_x_offset,
                y1=fallback_y_offset,
                x2=fallback_x_offset + new_width,
                y2=fallback_y_offset + new_height,
            )
        else:
            can_reuse_framing_metadata = (
                persisted_fixed_offsets is not None
                and persisted_crop_width == new_width
                and persisted_crop_height == new_height
            )
            if can_reuse_framing_metadata:
                reliable_face_frames = int(effective_framing_metadata.get("reliable_face_frames") or 0)
                fixed_offsets = persisted_fixed_offsets
            else:
                framing_analysis_source = "render_reanalysis"
                framing_analysis = analyze_clip_framing(
                    video,
                    start_time,
                    end_time,
                    face_detection_mode=face_detection_mode,
                    fallback_crop_position=fallback_crop_position,
                    face_anchor_profile=face_anchor_profile,
                    output_aspect_ratio=normalized_output_aspect_ratio,
                )
                effective_framing_metadata = dict(framing_analysis.get("framing_metadata") or effective_framing_metadata)
                effective_framing_metadata["crop_width"] = int(framing_analysis.get("crop_width") or new_width)
                effective_framing_metadata["crop_height"] = int(framing_analysis.get("crop_height") or new_height)
                effective_framing_metadata["fixed_crop_offsets"] = list(framing_analysis.get("fixed_crop_offsets") or [])
                effective_framing_metadata["tracking_points"] = list(framing_analysis.get("tracking_points") or [])
                crop_confidence = str(effective_framing_metadata.get("crop_confidence") or "none")
                detection_state = str(effective_framing_metadata.get("detection_state") or "none")
                fallback_crop_position = _normalize_fallback_crop_position(
                    effective_framing_metadata.get("fallback_crop_position")
                )
                face_anchor_profile = _normalize_face_anchor_profile(
                    effective_framing_metadata.get("face_anchor_profile")
                )
                tracking_points = list(framing_analysis.get("tracking_points") or [])
                reliable_face_frames = int(effective_framing_metadata.get("reliable_face_frames") or 0)
                fixed_offsets = tuple(
                    framing_analysis.get("fixed_crop_offsets")
                    or _get_fallback_crop_offsets(video.w, video.h, new_width, new_height, fallback_crop_position)
                )
                if reliable_face_frames <= 0:
                    fixed_offsets = _get_fallback_crop_offsets(
                        video.w,
                        video.h,
                        new_width,
                        new_height,
                        fallback_crop_position,
                    )

            should_use_face_crop = False
            if framing_mode == "prefer_face":
                should_use_face_crop = reliable_face_frames > 0
            elif crop_confidence in {"high", "medium"}:
                should_use_face_crop = True

            if should_use_face_crop:
                cropped_clip = clip.cropped(
                    x1=int(fixed_offsets[0]),
                    y1=int(fixed_offsets[1]),
                    x2=int(fixed_offsets[0]) + new_width,
                    y2=int(fixed_offsets[1]) + new_height,
                )
                crop_mode = "face-locked"
                crop_reason = crop_confidence if crop_confidence != "none" else (
                    "stable_face_lock" if tracking_points else detection_state
                )
            else:
                cropped_clip = clip.cropped(
                    x1=int(fixed_offsets[0]),
                    y1=int(fixed_offsets[1]),
                    x2=int(fixed_offsets[0]) + new_width,
                    y2=int(fixed_offsets[1]) + new_height,
                )
                crop_mode = f"fallback-{fallback_crop_position}"
                crop_reason = "low_confidence" if detection_state == "weak" else "no_reliable_face"

        logger.info(
            "framing_mode=%s crop=%s fallback=%s confidence=%s detection_state=%s reason=%s start=%.1fs end=%.1fs",
            framing_mode,
            crop_mode,
            fallback_crop_position,
            crop_confidence,
            detection_state,
            crop_reason,
            start_time,
            end_time,
        )

        # Add subtitles from cached word timings.
        final_clips = [cropped_clip]

        if add_subtitles:
            subtitle_clips = create_assemblyai_subtitles(
                video_path,
                start_time,
                end_time,
                new_width,
                new_height,
                font_family,
                font_size,
                font_color,
                subtitle_style=subtitle_style,
                word_timings_override=subtitle_word_timings,
            )
            final_clips.extend(subtitle_clips)

        # Compose and encode
        final_clip = CompositeVideoClip(final_clips) if len(final_clips) > 1 else cropped_clip

        processor = VideoProcessor(font_family, font_size, font_color)
        clip_encoding_candidates = processor.get_clip_render_encoding_candidates()
        selected_encoder_backend = ""
        selected_encoder_profile = ""
        last_encode_error: Optional[Exception] = None

        for encoding_candidate in clip_encoding_candidates:
            selected_encoder_backend = str(encoding_candidate.get("encoder_backend") or "")
            selected_encoder_profile = str(encoding_candidate.get("encoder_profile") or "")
            temp_audiofile = output_path.with_name(
                f"{output_path.stem}.{selected_encoder_profile or 'render'}.temp-audio.m4a"
            )
            try:
                final_clip.write_videofile(
                    str(output_path),
                    temp_audiofile=str(temp_audiofile),
                    remove_temp=True,
                    logger=None,
                    **dict(encoding_candidate.get("settings") or {}),
                )
                break
            except Exception as encode_error:
                last_encode_error = encode_error
                logger.warning(
                    "Clip encode failed using %s (%s); retrying if fallback remains: %s",
                    selected_encoder_backend,
                    selected_encoder_profile,
                    encode_error,
                )
                try:
                    output_path.unlink(missing_ok=True)
                except Exception:
                    pass
                try:
                    temp_audiofile.unlink(missing_ok=True)
                except Exception:
                    pass
        else:
            if last_encode_error is not None:
                raise last_encode_error

        # Cleanup
        final_clip.close()
        clip.close()
        video.close()

        if render_details_sink is not None:
            render_details_sink.update(
                {
                    "encoder_backend": selected_encoder_backend,
                    "encoder_profile": selected_encoder_profile,
                    "framing_analysis_source": framing_analysis_source,
                    "framing_metadata_reused": framing_analysis_source == "persisted_metadata",
                    "output_aspect_ratio": normalized_output_aspect_ratio,
                }
            )
        logger.info(f"Successfully created clip: {output_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to create clip: {e}")
        if error_collector is not None:
            error_collector.append(str(e))
        return False

def create_clips_from_segments(
    video_path: Union[Path, str],
    segments: List[Dict[str, Any]],
    output_dir: Union[Path, str],
    font_family: str = "THEBOLDFONT-FREEVERSION",
    font_size: int = 24,
    font_color: str = "#FFFFFF",
    subtitle_style: Optional[Dict[str, Any]] = None,
    output_aspect_ratio: str = "9:16",
    diagnostics: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    filename_prefix: Optional[str] = None,
    max_workers: int = 1,
) -> List[Dict[str, Any]]:
    """Create optimized video clips from segments."""
    video_path = Path(video_path)
    output_dir = Path(output_dir)
    logger.info(f"Creating {len(segments)} clips")

    output_dir.mkdir(parents=True, exist_ok=True)
    clips_info: List[Dict[str, Any]] = []
    clip_failures: List[Dict[str, Any]] = []
    resolved_filename_prefix = _format_clip_run_prefix(filename_prefix)

    total_segments = len(segments)
    parallel_workers = max(1, min(int(max_workers or 1), total_segments or 1))
    progress_state_lock = threading.Lock()
    completed_count = 0
    encoder_backend_counts: Dict[str, int] = {}
    encoder_profile_counts: Dict[str, int] = {}
    framing_analysis_source_counts: Dict[str, int] = {}

    def _emit_progress(event: Dict[str, Any]) -> None:
        if progress_callback:
            progress_callback(event)

    def render_segment(segment_index: int, segment: Dict[str, Any]) -> Dict[str, Any]:
        nonlocal completed_count

        clip_index = segment_index + 1
        try:
            logger.info(
                "Processing segment %s: start='%s', end='%s'",
                clip_index,
                segment.get("start_time"),
                segment.get("end_time"),
            )

            start_seconds = parse_timestamp_to_seconds(segment["start_time"])
            end_seconds = parse_timestamp_to_seconds(segment["end_time"])
            duration = end_seconds - start_seconds
            logger.info(
                "Segment %s duration: %.1fs (start: %ss, end: %ss)",
                clip_index,
                duration,
                start_seconds,
                end_seconds,
            )

            if duration <= 0:
                logger.warning(
                    "Skipping clip %s: invalid duration %.1fs (start: %ss, end: %ss)",
                    clip_index,
                    duration,
                    start_seconds,
                    end_seconds,
                )
                with progress_state_lock:
                    completed_count += 1
                    current_completed = completed_count
                _emit_progress(
                    {
                        "kind": "completed",
                        "clip_index": clip_index,
                        "clip_total": total_segments,
                        "completed_count": current_completed,
                        "stage_label": f"Skipped clip {clip_index} of {total_segments}",
                        "start_time": segment.get("start_time"),
                        "end_time": segment.get("end_time"),
                        "success": False,
                        "error": "invalid_duration",
                    }
                )
                return {"clip_index": clip_index, "clip_info": None, "failure": "invalid_duration", "render_details": {}}

            clip_filename = _build_clip_filename(
                clip_index=clip_index,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                filename_prefix=resolved_filename_prefix,
            )
            clip_path = output_dir / clip_filename
            with progress_state_lock:
                current_completed = completed_count
            _emit_progress(
                {
                    "kind": "started",
                    "clip_index": clip_index,
                    "clip_total": total_segments,
                    "completed_count": current_completed,
                    "stage_label": f"Rendering clip {clip_index} of {total_segments}",
                    "start_time": segment.get("start_time"),
                    "end_time": segment.get("end_time"),
                    "filename": clip_filename,
                }
            )

            clip_errors: List[str] = []
            render_details: Dict[str, Any] = {}
            success = create_optimized_clip(
                video_path,
                start_seconds,
                end_seconds,
                clip_path,
                True,
                font_family,
                font_size,
                font_color,
                subtitle_style,
                subtitle_word_timings=segment.get("subtitle_word_timings"),
                framing_mode_override=str(segment.get("framing_mode_override") or "auto"),
                framing_metadata=(
                    dict(segment.get("framing_metadata"))
                    if isinstance(segment.get("framing_metadata"), dict)
                    else None
                ),
                output_aspect_ratio=str(segment.get("output_aspect_ratio") or output_aspect_ratio),
                error_collector=clip_errors,
                render_details_sink=render_details,
            )

            if success:
                clip_info = {
                    "clip_id": clip_index,
                    "filename": clip_filename,
                    "path": str(clip_path),
                    "start_time": segment["start_time"],
                    "end_time": segment["end_time"],
                    "duration": duration,
                    "text": segment["text"],
                    "relevance_score": segment["relevance_score"],
                    "reasoning": segment["reasoning"],
                    "framing_metadata": segment.get("framing_metadata") or {},
                    "framing_mode_override": str(segment.get("framing_mode_override") or "auto"),
                    "encoder_backend": render_details.get("encoder_backend"),
                    "encoder_profile": render_details.get("encoder_profile"),
                    "framing_analysis_source": render_details.get("framing_analysis_source"),
                }
                logger.info("Created clip %s: %.1fs", clip_index, duration)
            else:
                clip_info = None
                logger.error("Failed to create clip %s", clip_index)

            with progress_state_lock:
                completed_count += 1
                current_completed = completed_count

            _emit_progress(
                {
                    "kind": "completed",
                    "clip_index": clip_index,
                    "clip_total": total_segments,
                    "completed_count": current_completed,
                    "stage_label": f"Rendered clip {clip_index} of {total_segments}",
                    "start_time": segment.get("start_time"),
                    "end_time": segment.get("end_time"),
                    "filename": clip_filename,
                    "success": success,
                }
            )

            return {
                "clip_index": clip_index,
                "clip_info": clip_info,
                "failure": clip_errors[-1] if clip_errors else None,
                "render_details": render_details,
            }
        except Exception as exc:
            logger.error("Error processing clip %s: %s", clip_index, exc)
            with progress_state_lock:
                completed_count += 1
                current_completed = completed_count
            _emit_progress(
                {
                    "kind": "completed",
                    "clip_index": clip_index,
                    "clip_total": total_segments,
                    "completed_count": current_completed,
                    "stage_label": f"Clip {clip_index} failed during render",
                    "start_time": segment.get("start_time"),
                    "end_time": segment.get("end_time"),
                    "success": False,
                    "error": str(exc),
                }
            )
            return {"clip_index": clip_index, "clip_info": None, "failure": str(exc), "render_details": {}}

    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
        futures = [
            executor.submit(render_segment, segment_index, segment)
            for segment_index, segment in enumerate(segments)
        ]
        for future in as_completed(futures):
            results.append(future.result())

    for result in sorted(results, key=lambda item: int(item.get("clip_index") or 0)):
        clip_info = result.get("clip_info")
        render_details = result.get("render_details") if isinstance(result.get("render_details"), dict) else {}
        if clip_info:
            clips_info.append(clip_info)
            if render_details.get("encoder_backend"):
                _increment_count(encoder_backend_counts, str(render_details["encoder_backend"]))
            if render_details.get("encoder_profile"):
                _increment_count(encoder_profile_counts, str(render_details["encoder_profile"]))
            if render_details.get("framing_analysis_source"):
                _increment_count(framing_analysis_source_counts, str(render_details["framing_analysis_source"]))
            continue
        clip_failures.append(
            {
                "clip_index": int(result.get("clip_index") or 0),
                "error": str(result.get("failure") or "unknown_error"),
            }
        )

    logger.info(f"Successfully created {len(clips_info)}/{len(segments)} clips")
    if diagnostics is not None:
        diagnostics.update(
            {
                "attempted_segments": len(segments),
                "created_clips": len(clips_info),
                "failed_segments": len(clip_failures),
                "failure_samples": clip_failures[:3],
                "parallel_workers": parallel_workers,
                "output_aspect_ratio": _normalize_output_aspect_ratio(output_aspect_ratio),
                "encoder_backend_counts": encoder_backend_counts,
                "encoder_profile_counts": encoder_profile_counts,
                "framing_analysis_source_counts": framing_analysis_source_counts,
            }
        )
    return clips_info

def get_available_transitions() -> List[str]:
    """Get list of available transition video files."""
    transitions_dir = Path(__file__).parent.parent / "transitions"
    if not transitions_dir.exists():
        logger.warning("Transitions directory not found")
        return []

    transition_files = []
    for file_path in transitions_dir.glob("*.mp4"):
        transition_files.append(str(file_path))

    logger.info(f"Found {len(transition_files)} transition files")
    return transition_files

def apply_transition_effect(clip1_path: Path, clip2_path: Path, transition_path: Path, output_path: Path) -> bool:
    """Apply transition effect between two clips using a transition video."""
    try:
        from moviepy import VideoFileClip, concatenate_videoclips, vfx

        # Load clips
        clip1 = VideoFileClip(str(clip1_path))
        clip2 = VideoFileClip(str(clip2_path))
        transition = VideoFileClip(str(transition_path))

        # Ensure transition duration is reasonable (max 1.5 seconds)
        transition_duration = min(1.5, transition.duration)
        transition = transition.subclipped(0, transition_duration)

        # Resize transition to match clip dimensions
        clip_size = clip1.size
        transition = transition.resized(clip_size)

        # Create fade effect with transition
        fade_duration = 0.5  # Half second fade

        # MoviePy v2 expects effect objects, not string names.
        clip1_faded = clip1.with_effects([vfx.FadeOut(fade_duration)])
        clip2_faded = clip2.with_effects([vfx.FadeIn(fade_duration)])

        # Combine: clip1 -> transition -> clip2
        final_clip = concatenate_videoclips([
            clip1_faded,
            transition,
            clip2_faded
        ], method="compose")

        # Write output
        processor = VideoProcessor()
        encoding_settings = processor.get_optimal_encoding_settings("high")

        final_clip.write_videofile(
            str(output_path),
            temp_audiofile=str(output_path.with_name(f"{output_path.stem}.transition.temp-audio.m4a")),
            remove_temp=True,
            logger=None,
            **encoding_settings
        )

        # Cleanup
        final_clip.close()
        clip1.close()
        clip2.close()
        transition.close()

        logger.info(f"Applied transition effect: {output_path}")
        return True

    except Exception as e:
        logger.error(f"Error applying transition effect: {e}")
        return False

def create_clips_with_transitions(
    video_path: Union[Path, str],
    segments: List[Dict[str, Any]],
    output_dir: Union[Path, str],
    font_family: str = "THEBOLDFONT-FREEVERSION",
    font_size: int = 24,
    font_color: str = "#FFFFFF",
    subtitle_style: Optional[Dict[str, Any]] = None,
    output_aspect_ratio: str = "9:16",
    diagnostics: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    filename_prefix: Optional[str] = None,
    max_workers: int = 1,
) -> List[Dict[str, Any]]:
    """Create video clips with transition effects between them."""
    video_path = Path(video_path)
    output_dir = Path(output_dir)
    logger.info(f"Creating {len(segments)} clips with transitions")

    # First create individual clips
    render_diagnostics: Dict[str, Any] = {}
    clips_info = create_clips_from_segments(
        video_path,
        segments,
        output_dir,
        font_family,
        font_size,
        font_color,
        subtitle_style,
        output_aspect_ratio,
        diagnostics=render_diagnostics,
        progress_callback=progress_callback,
        filename_prefix=filename_prefix,
        max_workers=1,
    )

    if len(clips_info) < 2:
        logger.info("Not enough clips to apply transitions")
        if diagnostics is not None:
            diagnostics.update(render_diagnostics)
            diagnostics["transitions_applied"] = 0
        return clips_info

    # Get available transitions
    transitions = get_available_transitions()
    if not transitions:
        logger.warning("No transition files found, returning clips without transitions")
        return clips_info

    # Create clips with transitions
    transition_output_dir = output_dir / "with_transitions"
    transition_output_dir.mkdir(parents=True, exist_ok=True)

    enhanced_clips = []
    transition_failures = 0

    for i, clip_info in enumerate(clips_info):
        if i == 0:
            # First clip - no transition before
            enhanced_clips.append(clip_info)
        else:
            # Apply transition before this clip
            prev_clip_path = Path(clips_info[i-1]["path"])
            current_clip_path = Path(clip_info["path"])

            # Select transition (cycle through available transitions)
            transition_path = Path(transitions[i % len(transitions)])

            # Create output path for clip with transition
            transition_filename = f"{Path(str(clip_info['filename'])).stem}_transition.mp4"
            transition_output_path = transition_output_dir / transition_filename

            success = apply_transition_effect(
                prev_clip_path,
                current_clip_path,
                transition_path,
                transition_output_path
            )

            if success:
                # Update clip info with transition version
                enhanced_clip_info = clip_info.copy()
                enhanced_clip_info["filename"] = transition_filename
                enhanced_clip_info["path"] = str(transition_output_path)
                enhanced_clip_info["has_transition"] = True
                enhanced_clips.append(enhanced_clip_info)
                logger.info(f"Added transition to clip {i+1}")
            else:
                # Fallback to original clip if transition fails
                enhanced_clips.append(clip_info)
                transition_failures += 1
                logger.warning(f"Failed to add transition to clip {i+1}, using original")

    logger.info(f"Successfully created {len(enhanced_clips)} clips with transitions")
    if diagnostics is not None:
        diagnostics.update(render_diagnostics)
        diagnostics["transitions_attempted"] = max(0, len(clips_info) - 1)
        diagnostics["transitions_failed"] = transition_failures
        diagnostics["transitions_applied"] = max(0, len(clips_info) - 1 - transition_failures)
    return enhanced_clips

# Backward compatibility functions
def get_video_transcript_with_assemblyai(path: Path) -> str:
    """Backward compatibility wrapper for older call sites."""
    return get_video_transcript(path, transcription_provider="assemblyai")

def create_9_16_clip(video_path: Path, start_time: float, end_time: float, output_path: Path, subtitle_text: str = "") -> bool:
    """Backward compatibility wrapper."""
    return create_optimized_clip(video_path, start_time, end_time, output_path, add_subtitles=bool(subtitle_text))
