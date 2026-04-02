"""
Utility functions for video-related operations.
Optimized for MoviePy v2, local transcription, and high-quality output.
"""

from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Union, Callable
import os
import logging
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import json
import hashlib
import threading
import urllib.request
import subprocess
import tempfile
import time
from difflib import SequenceMatcher
import re

import cv2
from moviepy import VideoFileClip, CompositeVideoClip, TextClip, ColorClip

try:
    import assemblyai as aai
except ImportError:  # pragma: no cover - optional provider
    aai = None
import srt
from datetime import timedelta

from .config import Config
from .subtitle_style import normalize_subtitle_style
from .whisper_runtime import resolve_whisper_device

logger = logging.getLogger(__name__)
config = Config()
_whisper_model_cache: Dict[str, Any] = {}
_whisper_model_lock = threading.Lock()
_face_model_path_lock = threading.Lock()
_face_model_path_cache: Optional[Path] = None
_mediapipe_detector_tls = threading.local()

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


def _extract_audio_chunk_for_whisper(
    video_path: Path,
    output_path: Path,
    start_seconds: float,
    end_seconds: float,
) -> None:
    duration_seconds = max(end_seconds - start_seconds, 0.05)
    cmd = [
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
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ]
    subprocess.run(cmd, check=True)


def _run_whisper_transcription(model: Any, media_path: Union[Path, str], use_fp16: bool) -> Dict[str, Any]:
    return model.transcribe(
        str(media_path),
        task="transcribe",
        word_timestamps=True,
        verbose=False,
        fp16=use_fp16,
    )


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

def detect_optimal_crop_region(video_clip: VideoFileClip, start_time: float, end_time: float, target_ratio: float = 9/16) -> Tuple[int, int, int, int]:
    """Detect optimal crop region using improved face detection."""
    try:
        original_width, original_height = video_clip.size

        # Calculate target dimensions and ensure they're even
        if original_width / original_height > target_ratio:
            new_width = round_to_even(int(original_height * target_ratio))
            new_height = round_to_even(original_height)
        else:
            new_width = round_to_even(original_width)
            new_height = round_to_even(int(original_width / target_ratio))

        # Try improved face detection
        face_centers = detect_faces_in_clip(video_clip, start_time, end_time)

        # Calculate crop position
        if face_centers:
            # Use weighted average of face centers with temporal consistency
            total_weight = sum(area * confidence for _, _, area, confidence in face_centers)
            if total_weight > 0:
                weighted_x = sum(x * area * confidence for x, y, area, confidence in face_centers) / total_weight
                weighted_y = sum(y * area * confidence for x, y, area, confidence in face_centers) / total_weight

                # Add slight bias towards upper portion for better face framing
                weighted_y = max(0, weighted_y - new_height * 0.1)

                x_offset = max(0, min(int(weighted_x - new_width // 2), original_width - new_width))
                y_offset = max(0, min(int(weighted_y - new_height // 2), original_height - new_height))

                logger.info(f"Face-centered crop: {len(face_centers)} faces detected with improved algorithm")
            else:
                # Center crop
                x_offset = (original_width - new_width) // 2 if original_width > new_width else 0
                y_offset = (original_height - new_height) // 2 if original_height > new_height else 0
        else:
            # Center crop
            x_offset = (original_width - new_width) // 2 if original_width > new_width else 0
            y_offset = (original_height - new_height) // 2 if original_height > new_height else 0
            logger.info("Using center crop (no faces detected)")

        # Ensure offsets are even too
        x_offset = round_to_even(x_offset)
        y_offset = round_to_even(y_offset)

        logger.info(f"Crop dimensions: {new_width}x{new_height} at offset ({x_offset}, {y_offset})")
        return (x_offset, y_offset, new_width, new_height)

    except Exception as e:
        logger.error(f"Error in crop detection: {e}")
        # Fallback to center crop
        original_width, original_height = video_clip.size
        if original_width / original_height > target_ratio:
            new_width = round_to_even(int(original_height * target_ratio))
            new_height = round_to_even(original_height)
        else:
            new_width = round_to_even(original_width)
            new_height = round_to_even(int(original_width / target_ratio))

        x_offset = round_to_even((original_width - new_width) // 2) if original_width > new_width else 0
        y_offset = round_to_even((original_height - new_height) // 2) if original_height > new_height else 0

        return (x_offset, y_offset, new_width, new_height)

def detect_faces_in_clip(video_clip: VideoFileClip, start_time: float, end_time: float) -> List[Tuple[int, int, int, float]]:
    """
    Improved face detection using multiple methods and temporal consistency.
    Returns list of (x, y, area, confidence) tuples.
    """
    face_centers = []

    try:
        mp_face_detection, mp_detection_backend, mp_module = _get_thread_mediapipe_face_detector()

        # Initialize OpenCV face detectors as fallback
        haar_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

        # Try to load DNN face detector (more accurate than Haar)
        dnn_net = None
        try:
            cv2_data_dir = Path(cv2.data.haarcascades)
            prototxt_path = cv2_data_dir / "opencv_face_detector.pbtxt"
            model_path = cv2_data_dir / "opencv_face_detector_uint8.pb"

            if prototxt_path.exists() and model_path.exists():
                dnn_net = cv2.dnn.readNetFromTensorflow(str(model_path), str(prototxt_path))
                logger.info("OpenCV DNN face detector loaded as backup")
            else:
                logger.info("OpenCV DNN face detector not available")
        except Exception as exc:
            logger.info(f"OpenCV DNN face detector failed to load: {exc}")

        # Sample more frames for better face detection (every 0.5 seconds)
        duration = end_time - start_time
        sample_interval = min(0.5, duration / 10)  # At least 10 samples, max every 0.5s
        sample_times = []

        current_time = start_time
        while current_time < end_time:
            sample_times.append(current_time)
            current_time += sample_interval

        # Ensure we always sample the middle and end
        if duration > 1.0:
            middle_time = start_time + duration / 2
            if middle_time not in sample_times:
                sample_times.append(middle_time)

        sample_times = [t for t in sample_times if t < end_time]
        logger.info(f"Sampling {len(sample_times)} frames for face detection")

        for sample_time in sample_times:
            try:
                frame = video_clip.get_frame(sample_time)
                height, width = frame.shape[:2]
                detected_faces = []

                # Try MediaPipe first (most accurate)
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
                        else:
                            # MediaPipe Solutions expects RGB format.
                            results = mp_face_detection.process(frame)
                            if results.detections:
                                for detection in results.detections:
                                    bbox = detection.location_data.relative_bounding_box
                                    confidence = detection.score[0]

                                    x = int(bbox.xmin * width)
                                    y = int(bbox.ymin * height)
                                    w = int(bbox.width * width)
                                    h = int(bbox.height * height)

                                    if w > 30 and h > 30:
                                        detected_faces.append((x, y, w, h, confidence))
                    except Exception as e:
                        logger.warning(f"MediaPipe detection failed for frame at {sample_time}s: {e}")

                # If MediaPipe didn't find faces, try DNN detector
                if not detected_faces and dnn_net is not None:
                    try:
                        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                        blob = cv2.dnn.blobFromImage(frame_bgr, 1.0, (300, 300), [104, 117, 123])
                        dnn_net.setInput(blob)
                        detections = dnn_net.forward()

                        for i in range(detections.shape[2]):
                            confidence = detections[0, 0, i, 2]
                            if confidence > 0.5:  # Confidence threshold
                                x1 = int(detections[0, 0, i, 3] * width)
                                y1 = int(detections[0, 0, i, 4] * height)
                                x2 = int(detections[0, 0, i, 5] * width)
                                y2 = int(detections[0, 0, i, 6] * height)

                                w = x2 - x1
                                h = y2 - y1

                                if w > 30 and h > 30:  # Minimum face size
                                    detected_faces.append((x1, y1, w, h, confidence))
                    except Exception as e:
                        logger.warning(f"DNN detection failed for frame at {sample_time}s: {e}")

                # If still no faces found, use Haar cascade
                if not detected_faces:
                    try:
                        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

                        faces = haar_cascade.detectMultiScale(
                            gray,
                            scaleFactor=1.05,  # More sensitive
                            minNeighbors=3,    # Less strict
                            minSize=(40, 40),  # Smaller minimum size
                            maxSize=(int(width*0.7), int(height*0.7))  # Maximum size limit
                        )

                        for (x, y, w, h) in faces:
                            # Estimate confidence based on face size and position
                            face_area = w * h
                            relative_size = face_area / (width * height)
                            confidence = min(0.9, 0.3 + relative_size * 2)  # Rough confidence estimate
                            detected_faces.append((x, y, w, h, confidence))
                    except Exception as e:
                        logger.warning(f"Haar cascade detection failed for frame at {sample_time}s: {e}")

                # Process detected faces
                for (x, y, w, h, confidence) in detected_faces:
                    face_center_x = x + w // 2
                    face_center_y = y + h // 2
                    face_area = w * h

                    # Filter out very small or very large faces
                    frame_area = width * height
                    relative_area = face_area / frame_area

                    if 0.005 < relative_area < 0.3:  # Face should be 0.5% to 30% of frame
                        face_centers.append((face_center_x, face_center_y, face_area, confidence))

            except Exception as e:
                logger.warning(f"Error detecting faces in frame at {sample_time}s: {e}")
                continue

        # Remove outliers (faces that are very far from the median position)
        if len(face_centers) > 2:
            face_centers = filter_face_outliers(face_centers)

        logger.info(f"Detected {len(face_centers)} reliable face centers")
        return face_centers

    except Exception as e:
        logger.error(f"Error in face detection: {e}")
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
) -> List[TextClip]:
    if not text or duration <= 0 or box_width <= 0 or box_height <= 0:
        return []

    layered_clips: List[TextClip] = []
    safe_opacity_scale = max(0.0, min(1.0, float(opacity_scale)))

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
                    shadow_clip.with_position((layer_x, layer_y)).with_opacity(
                        per_layer_opacity * safe_opacity_scale
                    )
                )

    if soft_stroke_clip is not None and soft_stroke_opacity > 0:
        layered_clips.append(
            soft_stroke_clip.with_position((base_x, base_y)).with_opacity(soft_stroke_opacity * safe_opacity_scale)
        )

    if stroke_text_clip is not None:
        layered_clips.append(
            stroke_text_clip.with_position((base_x, base_y)).with_opacity(max(0.01, safe_opacity_scale))
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
            fill_clip.with_position((layer_x, layer_y)).with_opacity(0.8 * safe_opacity_scale)
        )

    layered_clips.append(fill_clip.with_position((base_x, base_y)).with_opacity(max(0.01, safe_opacity_scale)))
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

        base_y = int(video_height * 0.70 - line_box_height // 2)
        max_y = max(0, video_height - line_box_height)
        base_y = max(0, min(base_y, max_y))

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
                opacity_scale=0.52,
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
                opacity_scale=1.0,
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
    error_collector: Optional[List[str]] = None,
) -> bool:
    """Create optimized 9:16 clip with word-timed subtitles."""
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

        # Get optimal crop
        x_offset, y_offset, new_width, new_height = detect_optimal_crop_region(
            video, start_time, end_time, target_ratio=9/16
        )

        cropped_clip = clip.cropped(
            x1=x_offset, y1=y_offset,
            x2=x_offset + new_width, y2=y_offset + new_height
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
        encoding_settings = processor.get_optimal_encoding_settings("high")

        final_clip.write_videofile(
            str(output_path),
            temp_audiofile='temp-audio.m4a',
            remove_temp=True,
            logger=None,
            **encoding_settings
        )

        # Cleanup
        final_clip.close()
        clip.close()
        video.close()

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
    diagnostics: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> List[Dict[str, Any]]:
    """Create optimized video clips from segments."""
    video_path = Path(video_path)
    output_dir = Path(output_dir)
    logger.info(f"Creating {len(segments)} clips")

    output_dir.mkdir(parents=True, exist_ok=True)
    clips_info = []
    clip_failures: List[Dict[str, Any]] = []

    total_segments = len(segments)
    for i, segment in enumerate(segments):
        try:
            # Debug log the segment data
            logger.info(f"Processing segment {i+1}: start='{segment.get('start_time')}', end='{segment.get('end_time')}'")

            start_seconds = parse_timestamp_to_seconds(segment['start_time'])
            end_seconds = parse_timestamp_to_seconds(segment['end_time'])

            duration = end_seconds - start_seconds
            logger.info(f"Segment {i+1} duration: {duration:.1f}s (start: {start_seconds}s, end: {end_seconds}s)")

            if duration <= 0:
                logger.warning(f"Skipping clip {i+1}: invalid duration {duration:.1f}s (start: {start_seconds}s, end: {end_seconds}s)")
                if progress_callback:
                    progress_callback(i + 1, total_segments)
                continue

            clip_filename = f"clip_{i+1}_{segment['start_time'].replace(':', '')}-{segment['end_time'].replace(':', '')}.mp4"
            clip_path = output_dir / clip_filename

            clip_errors: List[str] = []
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
                error_collector=clip_errors,
            )

            if success:
                clip_info = {
                    "clip_id": i + 1,
                    "filename": clip_filename,
                    "path": str(clip_path),
                    "start_time": segment['start_time'],
                    "end_time": segment['end_time'],
                    "duration": duration,
                    "text": segment['text'],
                    "relevance_score": segment['relevance_score'],
                    "reasoning": segment['reasoning']
                }
                clips_info.append(clip_info)
                logger.info(f"Created clip {i+1}: {duration:.1f}s")
            else:
                logger.error(f"Failed to create clip {i+1}")
                clip_failures.append(
                    {
                        "clip_index": i + 1,
                        "start_time": segment.get("start_time"),
                        "end_time": segment.get("end_time"),
                        "error": clip_errors[-1] if clip_errors else "unknown_error",
                    }
                )

            if progress_callback:
                progress_callback(i + 1, total_segments)

        except Exception as e:
            logger.error(f"Error processing clip {i+1}: {e}")
            clip_failures.append(
                {
                    "clip_index": i + 1,
                    "start_time": segment.get("start_time"),
                    "end_time": segment.get("end_time"),
                    "error": str(e),
                }
            )
            if progress_callback:
                progress_callback(i + 1, total_segments)

    logger.info(f"Successfully created {len(clips_info)}/{len(segments)} clips")
    if diagnostics is not None:
        diagnostics.update(
            {
                "attempted_segments": len(segments),
                "created_clips": len(clips_info),
                "failed_segments": len(clip_failures),
                "failure_samples": clip_failures[:3],
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
            temp_audiofile='temp-audio.m4a',
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
    diagnostics: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
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
        diagnostics=render_diagnostics,
        progress_callback=progress_callback,
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
            transition_filename = f"transition_{i}_{clip_info['filename']}"
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
