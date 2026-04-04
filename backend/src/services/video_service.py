"""
Video service - handles video processing business logic.
"""
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, Awaitable
import logging
import asyncio
import json
import math
import subprocess
from array import array

from ..utils.async_helpers import run_in_thread
from ..youtube_utils import (
    download_youtube_video,
    get_youtube_video_title,
    get_youtube_video_id
)
from ..ai_focus_tags import build_ai_focus_guidance
from ..ai import get_most_relevant_parts_by_transcript
from ..config import Config
from ..transcription_limits import (
    ASSEMBLYAI_MAX_DURATION_SECONDS,
    ASSEMBLYAI_MAX_LOCAL_UPLOAD_SIZE_BYTES,
)

logger = logging.getLogger(__name__)
config = Config()
WAVEFORM_MIN_BINS = 300
WAVEFORM_MAX_BINS = 12000
WAVEFORM_BASE_MIN_BINS = 12000
WAVEFORM_BASE_MAX_BINS = 120000
WAVEFORM_BASE_BINS_PER_SECOND = 4
WAVEFORM_SAMPLE_RATE_HZ = 2000


class VideoService:
    """Service for video processing operations."""

    @staticmethod
    def _video_utils_attr(name: str):
        # Keep heavy video/ML imports out of API startup path.
        from .. import video_utils

        return getattr(video_utils, name)

    @staticmethod
    def _is_retryable_zai_error(error_text: Optional[str]) -> bool:
        normalized = (error_text or "").strip().lower()
        if not normalized:
            return False
        retry_markers = (
            "insufficient balance",
            "no resource package",
            "\"code\": \"1113\"",
            "'code': '1113'",
            "code: 1113",
        )
        return any(marker in normalized for marker in retry_markers)

    @staticmethod
    async def download_video(url: str, progress_callback: Optional[callable] = None) -> Optional[Path]:
        """
        Download a YouTube video asynchronously.
        Runs the sync download_youtube_video in a thread pool.
        """
        logger.info(f"Starting video download: {url}")
        loop = asyncio.get_running_loop()

        def on_download_progress(download_percent: int, message: str):
            if not progress_callback:
                return

            # Download stage occupies 10%-30% of overall progress.
            overall_progress = 10 + int((max(0, min(100, download_percent)) / 100) * 20)
            is_cached = "skipping download" in message.lower() or "found existing download" in message.lower()
            asyncio.run_coroutine_threadsafe(
                progress_callback(
                    overall_progress,
                    message,
                    {
                        "stage": "download",
                        "stage_progress": max(0, min(100, download_percent)),
                        "overall_progress": overall_progress,
                        "cached": is_cached,
                    },
                ),
                loop,
            )

        video_path = await run_in_thread(download_youtube_video, url, 3, on_download_progress)

        if not video_path:
            logger.error(f"Failed to download video: {url}")
            return None

        logger.info(f"Video downloaded successfully: {video_path}")
        return video_path

    @staticmethod
    async def get_video_title(url: str) -> str:
        """
        Get video title asynchronously.
        Returns a default title if retrieval fails.
        """
        try:
            title = await run_in_thread(get_youtube_video_title, url)
            return title or "YouTube Video"
        except Exception as e:
            logger.warning(f"Failed to get video title: {e}")
            return "YouTube Video"

    @staticmethod
    async def generate_transcript(
        video_path: Path,
        transcription_provider: str = "local",
        assembly_api_key: Optional[str] = None,
        whisper_chunking_enabled: Optional[bool] = None,
        whisper_chunk_duration_seconds: Optional[int] = None,
        whisper_chunk_overlap_seconds: Optional[int] = None,
        whisper_device_preference: Optional[str] = None,
        whisper_gpu_index: Optional[int] = None,
        whisper_model_size: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> str:
        """
        Generate transcript from video using configured transcription provider.
        Runs in thread pool to avoid blocking.
        """
        logger.info(f"Generating transcript for: {video_path}")
        get_video_transcript = VideoService._video_utils_attr("get_video_transcript")
        transcript = await run_in_thread(
            get_video_transcript,
            str(video_path),
            transcription_provider,
            assembly_api_key,
            whisper_chunking_enabled,
            whisper_chunk_duration_seconds,
            whisper_chunk_overlap_seconds,
            whisper_device_preference,
            whisper_gpu_index,
            whisper_model_size,
            progress_callback,
        )
        logger.info(f"Transcript generated: {len(transcript)} characters")
        return transcript

    @staticmethod
    async def generate_transcript_with_progress(
        video_path: Path,
        progress_callback: Optional[callable] = None,
        transcription_provider: str = "local",
        assembly_api_key: Optional[str] = None,
        whisper_chunking_enabled: Optional[bool] = None,
        whisper_chunk_duration_seconds: Optional[int] = None,
        whisper_chunk_overlap_seconds: Optional[int] = None,
        whisper_device_preference: Optional[str] = None,
        whisper_gpu_index: Optional[int] = None,
        whisper_model_size: Optional[str] = None,
    ) -> str:
        """
        Generate transcript and emit heartbeat progress while waiting for transcription.
        This prevents the UI from appearing stuck during long transcription calls.
        """
        get_cached_formatted_transcript = VideoService._video_utils_attr("get_cached_formatted_transcript")
        cached_transcript = await run_in_thread(get_cached_formatted_transcript, str(video_path))
        if cached_transcript:
            logger.info(f"Using cached transcript for: {video_path.name}")
            if progress_callback:
                await progress_callback(
                    50,
                    "Found existing transcript, skipping transcription.",
                    {
                        "stage": "transcript",
                        "stage_progress": 100,
                        "overall_progress": 50,
                        "cached": True,
                        "transcription_provider": transcription_provider,
                    },
                )
            return cached_transcript

        heartbeat_task = None
        stop_heartbeat = asyncio.Event()
        loop = asyncio.get_running_loop()

        def on_transcription_progress(progress_event: Dict[str, Any]) -> None:
            if not progress_callback:
                return
            try:
                stage_progress = int(progress_event.get("stage_progress", 0) or 0)
                stage_progress = max(0, min(100, stage_progress))
                overall_progress = 30 + int((stage_progress / 100) * 20)
                message = str(progress_event.get("message") or "Generating transcript...")
                metadata = {
                    "stage": "transcript",
                    "stage_progress": stage_progress,
                    "overall_progress": overall_progress,
                    "transcription_provider": transcription_provider,
                    **progress_event,
                }
                future = asyncio.run_coroutine_threadsafe(
                    progress_callback(overall_progress, message, metadata),
                    loop,
                )

                def _log_callback_error(done_future: "asyncio.Future[Any]") -> None:
                    try:
                        done_future.result()
                    except Exception as exc:
                        logger.warning(f"Failed to publish transcription progress event: {exc}")

                future.add_done_callback(_log_callback_error)
            except Exception as exc:
                logger.warning(f"Failed to prepare transcription progress event: {exc}")

        async def heartbeat():
            # Transcript stage maps to overall progress range 30..50.
            overall = 31
            stage_progress = 5
            while not stop_heartbeat.is_set():
                if progress_callback:
                    await progress_callback(
                        min(overall, 49),
                        "Generating transcript...",
                        {
                            "stage": "transcript",
                            "stage_progress": min(stage_progress, 95),
                            "overall_progress": min(overall, 49),
                            "transcription_provider": transcription_provider,
                        },
                    )
                overall += 1
                stage_progress += 5
                try:
                    await asyncio.wait_for(stop_heartbeat.wait(), timeout=4)
                except asyncio.TimeoutError:
                    pass

        try:
            if progress_callback:
                heartbeat_task = asyncio.create_task(heartbeat())
            transcript = await VideoService.generate_transcript(
                video_path,
                transcription_provider=transcription_provider,
                assembly_api_key=assembly_api_key,
                whisper_chunking_enabled=whisper_chunking_enabled,
                whisper_chunk_duration_seconds=whisper_chunk_duration_seconds,
                whisper_chunk_overlap_seconds=whisper_chunk_overlap_seconds,
                whisper_device_preference=whisper_device_preference,
                whisper_gpu_index=whisper_gpu_index,
                whisper_model_size=whisper_model_size,
                progress_callback=on_transcription_progress,
            )
            return transcript
        finally:
            stop_heartbeat.set()
            if heartbeat_task:
                await heartbeat_task

    @staticmethod
    async def analyze_transcript(
        transcript: str,
        ai_provider: str = "openai",
        ai_api_key: Optional[str] = None,
        ai_base_url: Optional[str] = None,
        ai_model: Optional[str] = None,
        ai_focus_tags: Optional[List[str]] = None,
        ai_request_options: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Analyze transcript with AI to find relevant segments.
        This is already async, no need to wrap.
        """
        logger.info("Starting AI analysis of transcript")
        relevant_parts = await get_most_relevant_parts_by_transcript(
            transcript,
            ai_provider=ai_provider,
            ai_api_key=ai_api_key,
            ai_base_url=ai_base_url,
            ai_model=ai_model,
            ai_focus_tags=ai_focus_tags,
            ai_request_options=ai_request_options,
        )
        logger.info(f"AI analysis complete: {len(relevant_parts.most_relevant_segments)} segments found")
        return relevant_parts

    @staticmethod
    async def analyze_transcript_with_progress(
        transcript: str,
        ai_provider: str = "openai",
        ai_api_key: Optional[str] = None,
        ai_base_url: Optional[str] = None,
        ai_model: Optional[str] = None,
        ai_focus_tags: Optional[List[str]] = None,
        ai_request_options: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[callable] = None,
    ) -> Any:
        """
        Analyze transcript and emit heartbeat progress while waiting for the LLM call.
        This keeps UI progress moving during long AI analysis.
        """
        heartbeat_task = None
        stop_heartbeat = asyncio.Event()

        async def heartbeat():
            # Analysis stage maps to overall progress range 50..70.
            overall = 51
            stage_progress = 5
            while not stop_heartbeat.is_set():
                if progress_callback:
                    await progress_callback(
                        min(overall, 69),
                        f"Analyzing content with AI ({ai_provider})...",
                        {
                            "stage": "analysis",
                            "stage_progress": min(stage_progress, 95),
                            "overall_progress": min(overall, 69),
                            "ai_provider": ai_provider,
                        },
                    )
                overall += 1
                stage_progress += 5
                try:
                    await asyncio.wait_for(stop_heartbeat.wait(), timeout=3)
                except asyncio.TimeoutError:
                    pass

        try:
            if progress_callback:
                heartbeat_task = asyncio.create_task(heartbeat())
            return await VideoService.analyze_transcript(
                transcript,
                ai_provider=ai_provider,
                ai_api_key=ai_api_key,
                ai_base_url=ai_base_url,
                ai_model=ai_model,
                ai_focus_tags=ai_focus_tags,
                ai_request_options=ai_request_options,
            )
        finally:
            stop_heartbeat.set()
            if heartbeat_task:
                await heartbeat_task

    @staticmethod
    async def create_video_clips(
        video_path: Path,
        segments: List[Dict[str, Any]],
        font_family: str = "TikTokSans-Regular",
        font_size: int = 24,
        font_color: str = "#FFFFFF",
        subtitle_style: Optional[Dict[str, Any]] = None,
        transitions_enabled: bool = False,
        progress_callback: Optional[callable] = None,
        filename_prefix: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create video clips from segments with subtitles, with optional transitions.
        Runs in thread pool as video processing is CPU-intensive.
        """
        logger.info(
            "Creating %s video clips (transitions_enabled=%s)",
            len(segments),
            transitions_enabled,
        )
        clips_output_dir = Path(config.temp_dir) / "clips"
        clips_output_dir.mkdir(parents=True, exist_ok=True)
        render_diagnostics: Dict[str, Any] = {}
        loop = asyncio.get_running_loop()

        def on_clip_progress(event: Dict[str, Any]) -> None:
            if not progress_callback:
                return
            total = int(event.get("clip_total") or 0)
            clip_index = int(event.get("clip_index") or 0)
            kind = str(event.get("kind") or "completed").strip().lower()
            if total <= 0:
                return
            completed = clip_index - 1 if kind == "started" else clip_index
            pct = int((max(0, min(total, completed)) / total) * 100)
            stage_progress = max(0, min(100, pct))
            overall_progress = 70 + int((stage_progress / 100) * 25)  # 70..95
            stage_label = str(event.get("stage_label") or f"Rendering clip {clip_index} of {total}")
            asyncio.run_coroutine_threadsafe(
                progress_callback(
                    overall_progress,
                    stage_label,
                    {
                        "stage": "clips",
                        "stage_progress": stage_progress,
                        "overall_progress": overall_progress,
                        "clip_index": clip_index,
                        "clip_total": total,
                        "stage_label": stage_label,
                        "clip_started": kind == "started",
                        "clip_completed": kind != "started",
                        "start_time": event.get("start_time"),
                        "end_time": event.get("end_time"),
                        "filename": event.get("filename"),
                        "success": event.get("success"),
                    },
                ),
                loop,
            )

        create_clips_with_transitions = VideoService._video_utils_attr("create_clips_with_transitions")
        create_clips_from_segments = VideoService._video_utils_attr("create_clips_from_segments")
        clip_builder = create_clips_with_transitions if transitions_enabled else create_clips_from_segments
        clips_info = await run_in_thread(
            clip_builder,
            video_path,
            segments,
            clips_output_dir,
            font_family,
            font_size,
            font_color,
            subtitle_style,
            render_diagnostics,
            on_clip_progress,
            filename_prefix,
        )
        if not transitions_enabled:
            render_diagnostics["transitions_disabled"] = True

        logger.info(f"Successfully created {len(clips_info)} clips")
        return {"clips": clips_info, "diagnostics": render_diagnostics}

    @staticmethod
    async def align_edited_subtitle_words(
        video_path: Path,
        clip_start: float,
        clip_end: float,
        edited_text: str,
    ) -> List[Dict[str, Any]]:
        """Align edited subtitle text to clip audio at word granularity."""
        align_text_to_audio = VideoService._video_utils_attr("align_edited_text_to_clip_audio")
        return await run_in_thread(
            align_text_to_audio,
            video_path,
            clip_start,
            clip_end,
            edited_text,
        )

    @staticmethod
    async def analyze_segments_framing(
        video_path: Path,
        segments: List[Dict[str, Any]],
        face_detection_mode: str = "balanced",
        fallback_crop_position: str = "center",
    ) -> List[Dict[str, Any]]:
        analyze_segment_framing = VideoService._video_utils_attr("analyze_segment_framing_batch")
        return await run_in_thread(
            analyze_segment_framing,
            video_path,
            segments,
            face_detection_mode,
            fallback_crop_position,
        )

    @staticmethod
    async def analyze_single_segment_framing(
        video_path: Path,
        start_time: str,
        end_time: str,
        face_detection_mode: str = "balanced",
        fallback_crop_position: str = "center",
    ) -> Dict[str, Any]:
        analyze_segment_framing = VideoService._video_utils_attr("analyze_single_segment_framing")
        return await run_in_thread(
            analyze_segment_framing,
            video_path,
            start_time,
            end_time,
            face_detection_mode,
            fallback_crop_position,
        )

    @staticmethod
    def determine_source_type(url: str) -> str:
        """Determine if source is YouTube or uploaded file."""
        video_id = get_youtube_video_id(url)
        return "youtube" if video_id else "video_url"

    @staticmethod
    def validate_uploaded_video_path(url: str) -> Path:
        """
        Validate that uploaded video paths stay within the managed uploads directory.
        Prevents processing arbitrary local filesystem paths.
        """
        uploads_dir = (Path(config.temp_dir) / "uploads").resolve()
        candidate_path = Path(url).expanduser()
        resolved_path = candidate_path.resolve()

        # Ensure file exists and is inside uploads directory.
        if not resolved_path.exists() or not resolved_path.is_file():
            raise ValueError("Video file not found")

        try:
            resolved_path.relative_to(uploads_dir)
        except ValueError as exc:
            raise ValueError("Invalid uploaded video path") from exc

        return resolved_path

    @staticmethod
    async def resolve_video_path(
        url: str,
        source_type: str,
        progress_callback: Optional[callable] = None,
    ) -> Path:
        """Resolve a source URL to a local video path."""
        if progress_callback:
            await progress_callback(
                10,
                "Downloading video...",
                {"stage": "download", "stage_progress": 0, "overall_progress": 10},
            )

        if source_type == "youtube":
            video_path = await VideoService.download_video(url, progress_callback=progress_callback)
            if not video_path:
                raise Exception("Failed to download video")
            return video_path

        return VideoService.validate_uploaded_video_path(url)

    @staticmethod
    def _probe_media_duration_seconds(video_path: Path) -> float:
        command = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise RuntimeError(f"ffprobe failed for {video_path.name}: {stderr or 'unknown error'}")
        try:
            duration = float((result.stdout or "").strip())
        except ValueError as exc:
            raise RuntimeError(f"Invalid duration from ffprobe for {video_path.name}") from exc
        if not math.isfinite(duration) or duration <= 0:
            raise RuntimeError(f"Non-positive duration for {video_path.name}")
        return duration

    @staticmethod
    def _resolve_transcription_provider_for_media(
        requested_provider: str,
        video_path: Path,
    ) -> Dict[str, Any]:
        normalized_requested = (requested_provider or "local").strip().lower()
        if normalized_requested not in {"local", "assemblyai"}:
            logger.warning(
                "Unknown transcription provider '%s' for media preflight; defaulting to local",
                normalized_requested,
            )
            normalized_requested = "local"

        if normalized_requested != "assemblyai":
            return {
                "requested_provider": normalized_requested,
                "effective_provider": normalized_requested,
                "fallback_applied": False,
            }

        file_size_bytes = int(video_path.stat().st_size)
        duration_seconds: Optional[float] = None
        duration_probe_error: Optional[str] = None
        try:
            duration_seconds = VideoService._probe_media_duration_seconds(video_path)
        except Exception as exc:
            duration_probe_error = str(exc)
            logger.warning(
                "Failed to probe media duration for AssemblyAI preflight (%s): %s",
                video_path.name,
                exc,
            )

        size_exceeded = file_size_bytes > ASSEMBLYAI_MAX_LOCAL_UPLOAD_SIZE_BYTES
        duration_exceeded = (
            duration_seconds is not None and duration_seconds > ASSEMBLYAI_MAX_DURATION_SECONDS
        )
        fallback_applied = bool(size_exceeded or duration_exceeded)
        effective_provider = "local" if fallback_applied else "assemblyai"

        limit_messages: List[str] = []
        if size_exceeded:
            limit_messages.append(
                "file size exceeds AssemblyAI local upload limit "
                f"({file_size_bytes}B > {ASSEMBLYAI_MAX_LOCAL_UPLOAD_SIZE_BYTES}B)"
            )
        if duration_exceeded:
            limit_messages.append(
                "duration exceeds AssemblyAI limit "
                f"({duration_seconds:.1f}s > {ASSEMBLYAI_MAX_DURATION_SECONDS}s)"
            )

        reason = "; ".join(limit_messages) if limit_messages else None
        if fallback_applied:
            logger.info(
                "AssemblyAI preflight fallback for %s: %s; using local Whisper",
                video_path.name,
                reason,
            )

        return {
            "requested_provider": normalized_requested,
            "effective_provider": effective_provider,
            "fallback_applied": fallback_applied,
            "reason": reason,
            "file_size_bytes": file_size_bytes,
            "duration_seconds": duration_seconds,
            "duration_probe_error": duration_probe_error,
        }

    @staticmethod
    def _waveform_base_cache_path(video_path: Path) -> Path:
        return video_path.with_suffix(".waveform_base.json")

    @staticmethod
    def _load_waveform_base_cache(video_path: Path) -> Optional[Dict[str, Any]]:
        cache_path = VideoService._waveform_base_cache_path(video_path)
        if not cache_path.exists():
            return None

        try:
            raw_payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if not isinstance(raw_payload, dict):
                return None

            file_mtime = video_path.stat().st_mtime
            cache_video_mtime = raw_payload.get("video_mtime")
            if not isinstance(cache_video_mtime, (int, float)):
                return None
            if abs(float(cache_video_mtime) - float(file_mtime)) > 1e-3:
                return None

            bins_raw = raw_payload.get("bins")
            if not isinstance(bins_raw, int):
                return None
            bins = int(bins_raw)
            if bins <= 0:
                return None

            peaks_raw = raw_payload.get("peaks")
            if not isinstance(peaks_raw, list):
                return None
            peaks = [max(0.0, min(1.0, float(value))) for value in peaks_raw if isinstance(value, (int, float))]
            if len(peaks) != bins or len(peaks) == 0:
                return None

            duration_seconds = raw_payload.get("duration_seconds")
            if not isinstance(duration_seconds, (int, float)):
                return None

            return {
                "duration_seconds": float(duration_seconds),
                "bins": bins,
                "peaks": peaks,
            }
        except Exception as cache_error:
            logger.warning("Failed to load waveform cache %s: %s", cache_path, cache_error)
            return None

    @staticmethod
    def _save_waveform_base_cache(video_path: Path, payload: Dict[str, Any]) -> None:
        cache_path = VideoService._waveform_base_cache_path(video_path)
        temporary_path = cache_path.with_suffix(f"{cache_path.suffix}.tmp")
        try:
            cache_payload = {
                "video_mtime": video_path.stat().st_mtime,
                "duration_seconds": payload["duration_seconds"],
                "bins": payload["bins"],
                "peaks": payload["peaks"],
            }
            temporary_path.write_text(json.dumps(cache_payload), encoding="utf-8")
            temporary_path.replace(cache_path)
        except Exception as cache_error:
            logger.warning("Failed to save waveform cache %s: %s", cache_path, cache_error)
            try:
                if temporary_path.exists():
                    temporary_path.unlink()
            except Exception:
                pass

    @staticmethod
    def _normalize_requested_bins(bins: int) -> int:
        return max(WAVEFORM_MIN_BINS, min(WAVEFORM_MAX_BINS, int(bins)))

    @staticmethod
    def _normalize_base_bins(duration_seconds: float) -> int:
        estimated = int(max(1.0, duration_seconds) * WAVEFORM_BASE_BINS_PER_SECOND)
        return max(WAVEFORM_BASE_MIN_BINS, min(WAVEFORM_BASE_MAX_BINS, estimated))

    @staticmethod
    def _compute_waveform_peaks(video_path: Path, bins: int) -> Dict[str, Any]:
        duration_seconds = VideoService._probe_media_duration_seconds(video_path)
        total_expected_samples = max(1, int(duration_seconds * WAVEFORM_SAMPLE_RATE_HZ))
        samples_per_bin = max(1, math.ceil(total_expected_samples / bins))
        peaks: List[float] = [0.0] * bins

        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video_path),
            "-map",
            "a:0?",
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(WAVEFORM_SAMPLE_RATE_HZ),
            "-f",
            "s16le",
            "pipe:1",
        ]

        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if process.stdout is None:
            raise RuntimeError("Failed to read ffmpeg stdout for waveform generation")

        sample_index = 0
        pending_byte = b""

        try:
            while True:
                chunk = process.stdout.read(65536)
                if not chunk:
                    break

                raw_chunk = pending_byte + chunk
                if len(raw_chunk) % 2 != 0:
                    pending_byte = raw_chunk[-1:]
                    raw_chunk = raw_chunk[:-1]
                else:
                    pending_byte = b""

                if not raw_chunk:
                    continue

                values = array("h")
                values.frombytes(raw_chunk)
                if values.itemsize != 2:
                    raise RuntimeError("Unexpected sample width while generating waveform")

                for sample in values:
                    bin_index = min(bins - 1, sample_index // samples_per_bin)
                    normalized = abs(int(sample)) / 32768.0
                    if normalized > peaks[bin_index]:
                        peaks[bin_index] = normalized
                    sample_index += 1
        finally:
            try:
                process.stdout.close()
            except Exception:
                pass

        stderr_output = process.stderr.read().decode("utf-8", errors="ignore") if process.stderr else ""
        return_code = process.wait()
        if return_code != 0:
            raise RuntimeError(f"ffmpeg waveform extraction failed: {stderr_output.strip() or 'unknown error'}")

        if sample_index <= 0:
            # Video has no audio stream (or fully silent stream); return a valid empty waveform.
            return {
                "duration_seconds": duration_seconds,
                "bins": bins,
                "peaks": [0.0] * bins,
            }

        measured_duration = sample_index / WAVEFORM_SAMPLE_RATE_HZ
        duration_seconds = max(duration_seconds, measured_duration)
        return {
            "duration_seconds": duration_seconds,
            "bins": bins,
            "peaks": peaks,
        }

    @staticmethod
    def _resample_peaks_max(peaks: List[float], target_bins: int) -> List[float]:
        if target_bins <= 0:
            return []
        if not peaks:
            return [0.0] * target_bins

        source_bins = len(peaks)
        if source_bins == target_bins:
            return peaks

        resampled: List[float] = []
        for index in range(target_bins):
            start_index = int((index * source_bins) / target_bins)
            end_index = int(((index + 1) * source_bins) / target_bins)
            if end_index <= start_index:
                end_index = min(source_bins, start_index + 1)
            window = peaks[start_index:end_index]
            resampled.append(max(window) if window else peaks[min(source_bins - 1, start_index)])
        return resampled

    @staticmethod
    def _get_waveform_base_sync(video_path: Path) -> Dict[str, Any]:
        cached_payload = VideoService._load_waveform_base_cache(video_path)
        if cached_payload is not None:
            return cached_payload

        duration_seconds = VideoService._probe_media_duration_seconds(video_path)
        base_bins = VideoService._normalize_base_bins(duration_seconds)
        payload = VideoService._compute_waveform_peaks(video_path, base_bins)
        VideoService._save_waveform_base_cache(video_path, payload)
        return payload

    @staticmethod
    def _slice_waveform_window(
        base_payload: Dict[str, Any],
        bins: int,
        start_seconds: Optional[float],
        end_seconds: Optional[float],
    ) -> Dict[str, Any]:
        duration_seconds = float(base_payload["duration_seconds"])
        base_peaks = list(base_payload["peaks"])
        base_bins = max(1, len(base_peaks))

        window_start = 0.0 if start_seconds is None else max(0.0, min(duration_seconds, float(start_seconds)))
        window_end = duration_seconds if end_seconds is None else max(0.0, min(duration_seconds, float(end_seconds)))
        if window_end <= window_start:
            min_end = min(duration_seconds, window_start + max(1.0, duration_seconds / base_bins))
            window_end = max(min_end, window_start)

        start_ratio = 0.0 if duration_seconds <= 0 else window_start / duration_seconds
        end_ratio = 1.0 if duration_seconds <= 0 else window_end / duration_seconds
        start_index = max(0, min(base_bins - 1, int(math.floor(start_ratio * base_bins))))
        end_index = max(start_index + 1, min(base_bins, int(math.ceil(end_ratio * base_bins))))
        window_peaks = base_peaks[start_index:end_index] or [0.0]

        requested_bins = VideoService._normalize_requested_bins(bins)
        normalized_bins = min(requested_bins, max(1, len(window_peaks)))
        peaks = VideoService._resample_peaks_max(window_peaks, normalized_bins)
        return {
            "duration_seconds": duration_seconds,
            "range_start_seconds": window_start,
            "range_end_seconds": window_end,
            "bins": normalized_bins,
            "peaks": peaks,
        }

    @staticmethod
    def _get_waveform_data_sync(
        video_path: Path,
        bins: int,
        start_seconds: Optional[float] = None,
        end_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        base_payload = VideoService._get_waveform_base_sync(video_path)
        return VideoService._slice_waveform_window(base_payload, bins, start_seconds, end_seconds)

    @staticmethod
    async def get_waveform_data(
        video_path: Path,
        bins: int = 3000,
        start_seconds: Optional[float] = None,
        end_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Build (or load cached) waveform peak data for timeline rendering."""
        return await run_in_thread(
            VideoService._get_waveform_data_sync,
            video_path,
            bins,
            start_seconds,
            end_seconds,
        )

    @staticmethod
    async def _analyze_transcript_with_retries(
        transcript: str,
        ai_provider: str,
        ai_api_key: Optional[str],
        ai_base_url: Optional[str],
        ai_api_key_fallbacks: Optional[List[str]],
        ai_key_labels: Optional[List[str]],
        ai_routing_mode: Optional[str],
        ai_model: Optional[str],
        ai_focus_tags: Optional[List[str]],
        ai_request_options: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[callable] = None,
    ) -> tuple[Any, List[str]]:
        key_attempts = [ai_api_key] + list(ai_api_key_fallbacks or [])
        if not key_attempts:
            key_attempts = [None]

        labels = list(ai_key_labels or [])
        while len(labels) < len(key_attempts):
            labels.append(f"attempt-{len(labels) + 1}")

        relevant_parts = None
        attempted_labels: List[str] = []
        ollama_retries_used = 0
        ollama_max_retries = 0
        ollama_backoff_ms = 0
        if ai_provider == "ollama" and isinstance(ai_request_options, dict):
            try:
                ollama_max_retries = max(0, int(ai_request_options.get("ollama_max_retries", 0) or 0))
            except (TypeError, ValueError):
                ollama_max_retries = 0
            try:
                ollama_backoff_ms = max(0, int(ai_request_options.get("ollama_retry_backoff_ms", 0) or 0))
            except (TypeError, ValueError):
                ollama_backoff_ms = 0

        for attempt_index, key_candidate in enumerate(key_attempts):
            attempt_label = labels[attempt_index]
            attempted_labels.append(attempt_label)
            network_attempt = 0
            while True:
                try:
                    relevant_parts = await VideoService.analyze_transcript_with_progress(
                        transcript,
                        ai_provider=ai_provider,
                        ai_api_key=key_candidate,
                        ai_base_url=ai_base_url,
                        ai_model=ai_model,
                        ai_focus_tags=ai_focus_tags,
                        ai_request_options=ai_request_options,
                        progress_callback=progress_callback,
                    )
                    break
                except Exception as exc:
                    can_retry_network = (
                        ai_provider == "ollama"
                        and network_attempt < ollama_max_retries
                    )
                    if not can_retry_network:
                        raise
                    network_attempt += 1
                    ollama_retries_used += 1
                    delay_seconds = (ollama_backoff_ms * network_attempt) / 1000.0
                    logger.warning(
                        "Ollama analysis network attempt %s failed; retrying in %.2fs: %s",
                        network_attempt,
                        delay_seconds,
                        exc,
                    )
                    if progress_callback:
                        await progress_callback(
                            50,
                            f"Ollama request failed, retrying ({network_attempt}/{ollama_max_retries})...",
                            {
                                "stage": "analysis",
                                "stage_progress": 0,
                                "overall_progress": 50,
                                "ai_provider": ai_provider,
                                "retry_attempt": network_attempt,
                                "retry_max": ollama_max_retries,
                            },
                        )
                    if delay_seconds > 0:
                        await asyncio.sleep(delay_seconds)
            diagnostics = getattr(relevant_parts, "diagnostics", {}) or {}
            error_text = diagnostics.get("error")
            can_retry = (
                ai_provider == "zai"
                and attempt_index < (len(key_attempts) - 1)
                and VideoService._is_retryable_zai_error(error_text)
            )
            if not can_retry:
                break

            logger.warning(
                "z.ai analysis attempt %s failed due to balance/package issue; retrying with fallback key",
                attempt_label,
            )
            if progress_callback:
                await progress_callback(
                    50,
                    "z.ai key exhausted, retrying with fallback key...",
                    {
                        "stage": "analysis",
                        "stage_progress": 0,
                        "overall_progress": 50,
                        "ai_provider": ai_provider,
                        "ai_key_attempt": attempt_label,
                        "ai_routing_mode": ai_routing_mode,
                    },
                )

        if relevant_parts is None:
            raise RuntimeError("AI analysis failed to produce a result")

        diagnostics = getattr(relevant_parts, "diagnostics", {}) or {}
        diagnostics["ai_key_attempts"] = attempted_labels
        diagnostics["ai_key_label"] = attempted_labels[-1] if attempted_labels else "attempt-1"
        if ai_provider == "ollama":
            diagnostics["ollama_network_retries_used"] = ollama_retries_used
            diagnostics["ollama_network_max_retries"] = ollama_max_retries
            diagnostics["ollama_network_backoff_ms"] = ollama_backoff_ms
        if ai_routing_mode:
            diagnostics["ai_routing_mode"] = ai_routing_mode
        if ai_focus_tags:
            diagnostics["ai_focus_tags"] = list(ai_focus_tags)
        relevant_parts.diagnostics = diagnostics

        return relevant_parts, attempted_labels

    @staticmethod
    async def process_video_analysis(
        url: str,
        source_type: str,
        transcription_provider: str = "local",
        assembly_api_key: Optional[str] = None,
        ai_provider: str = "openai",
        ai_api_key: Optional[str] = None,
        ai_base_url: Optional[str] = None,
        ai_api_key_fallbacks: Optional[List[str]] = None,
        ai_key_labels: Optional[List[str]] = None,
        ai_routing_mode: Optional[str] = None,
        ai_model: Optional[str] = None,
        ai_request_options: Optional[Dict[str, Any]] = None,
        transcription_options: Optional[Dict[str, Any]] = None,
        ai_focus_tags: Optional[List[str]] = None,
        default_framing_mode: str = "auto",
        face_detection_mode: str = "balanced",
        fallback_crop_position: str = "center",
        progress_callback: Optional[callable] = None,
        cancel_check: Optional[Callable[[], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """Run download + transcription + AI analysis and return clip draft segments."""
        async def ensure_not_cancelled() -> None:
            if cancel_check:
                await cancel_check()

        await ensure_not_cancelled()
        video_path = await VideoService.resolve_video_path(
            url=url,
            source_type=source_type,
            progress_callback=progress_callback,
        )
        await ensure_not_cancelled()

        if progress_callback:
            await progress_callback(
                30,
                "Preparing audio for transcription...",
                {
                    "stage": "transcript",
                    "stage_progress": 0,
                    "overall_progress": 30,
                    "transcription_provider": transcription_provider,
                    "source_type": source_type,
                    "video_ready": True,
                },
            )

        provider_resolution = await run_in_thread(
            VideoService._resolve_transcription_provider_for_media,
            transcription_provider,
            video_path,
        )
        effective_transcription_provider = str(
            provider_resolution.get("effective_provider") or "local"
        )
        requested_transcription_provider = str(
            provider_resolution.get("requested_provider") or transcription_provider or "local"
        )

        if progress_callback and provider_resolution.get("fallback_applied"):
            await progress_callback(
                30,
                "AssemblyAI limits exceeded, switching to local Whisper transcription.",
                {
                    "stage": "transcript",
                    "stage_progress": 0,
                    "overall_progress": 30,
                    "transcription_provider": effective_transcription_provider,
                    "requested_transcription_provider": requested_transcription_provider,
                    "provider_fallback": True,
                    "provider_fallback_reason": provider_resolution.get("reason"),
                    "file_size_bytes": provider_resolution.get("file_size_bytes"),
                    "duration_seconds": provider_resolution.get("duration_seconds"),
                },
            )

        if progress_callback:
            await progress_callback(
                30,
                f"Generating transcript ({effective_transcription_provider})...",
                {
                    "stage": "transcript",
                    "stage_progress": 0,
                    "overall_progress": 30,
                    "transcription_provider": effective_transcription_provider,
                    "requested_transcription_provider": requested_transcription_provider,
                    "provider_fallback": bool(provider_resolution.get("fallback_applied")),
                },
            )

        transcript = await VideoService.generate_transcript_with_progress(
            video_path,
            progress_callback=progress_callback,
            transcription_provider=effective_transcription_provider,
            assembly_api_key=assembly_api_key,
            whisper_chunking_enabled=(
                transcription_options.get("whisper_chunking_enabled")
                if transcription_options
                else None
            ),
            whisper_chunk_duration_seconds=(
                transcription_options.get("whisper_chunk_duration_seconds")
                if transcription_options
                else None
            ),
            whisper_chunk_overlap_seconds=(
                transcription_options.get("whisper_chunk_overlap_seconds")
                if transcription_options
                else None
            ),
            whisper_device_preference=(
                transcription_options.get("whisper_device")
                if transcription_options
                else None
            ),
            whisper_gpu_index=(
                transcription_options.get("whisper_gpu_index")
                if transcription_options
                else None
            ),
            whisper_model_size=(
                transcription_options.get("whisper_model_size")
                if transcription_options
                else None
            ),
        )
        await ensure_not_cancelled()

        if progress_callback:
            focus_guidance = build_ai_focus_guidance(ai_focus_tags or [])
            guidance_suffix = " with focus tags" if focus_guidance else ""
            await progress_callback(
                50,
                f"Analyzing content with AI ({ai_provider}){guidance_suffix}...",
                {
                    "stage": "analysis",
                    "stage_progress": 0,
                    "overall_progress": 50,
                    "ai_provider": ai_provider,
                    "ai_focus_tags": list(ai_focus_tags or []),
                },
            )

        relevant_parts, _attempts = await VideoService._analyze_transcript_with_retries(
            transcript=transcript,
            ai_provider=ai_provider,
            ai_api_key=ai_api_key,
            ai_base_url=ai_base_url,
            ai_api_key_fallbacks=ai_api_key_fallbacks,
            ai_key_labels=ai_key_labels,
            ai_routing_mode=ai_routing_mode,
            ai_model=ai_model,
            ai_focus_tags=ai_focus_tags,
            ai_request_options=ai_request_options,
            progress_callback=progress_callback,
        )
        await ensure_not_cancelled()

        segments_json = [
            {
                "start_time": segment.start_time,
                "end_time": segment.end_time,
                "text": segment.text,
                "relevance_score": segment.relevance_score,
                "reasoning": segment.reasoning,
                "framing_mode_override": default_framing_mode,
            }
            for segment in relevant_parts.most_relevant_segments
        ]

        if segments_json:
            try:
                if progress_callback:
                    await progress_callback(
                        60,
                        "Evaluating clip framing...",
                        {"stage": "analysis", "stage_progress": 60, "overall_progress": 60},
                    )
                framing_results = await VideoService.analyze_segments_framing(
                    video_path,
                    segments_json,
                    face_detection_mode=face_detection_mode,
                    fallback_crop_position=fallback_crop_position,
                )
                for segment, framing_metadata in zip(segments_json, framing_results):
                    metadata = dict(framing_metadata or {})
                    metadata["fallback_crop_position"] = str(
                        metadata.get("fallback_crop_position") or fallback_crop_position or "center"
                    )
                    segment["framing_metadata"] = metadata
                    segment["framing_mode_override"] = default_framing_mode
                    segment["review_score"] = round(
                        max(0.0, min(1.0, float(segment.get("relevance_score") or 0.0) + float(metadata.get("score_adjustment") or 0.0))),
                        4,
                    )
                segments_json.sort(
                    key=lambda item: (
                        -float(item.get("review_score") or item.get("relevance_score") or 0.0),
                        str(item.get("start_time") or ""),
                    )
                )
            except Exception as framing_error:
                logger.warning("Failed to evaluate framing metadata: %s", framing_error)
                for segment in segments_json:
                    segment["framing_metadata"] = {
                        "fallback_crop_position": str(fallback_crop_position or "center"),
                    }
                    segment["framing_mode_override"] = default_framing_mode
                    segment["review_score"] = round(float(segment.get("relevance_score") or 0.0), 4)

        if progress_callback:
            await progress_callback(
                70,
                "Analysis complete. Preparing clips...",
                {"stage": "analysis", "stage_progress": 100, "overall_progress": 70},
            )

        return {
            "video_path": str(video_path),
            "segments": segments_json,
            "summary": relevant_parts.summary if relevant_parts else None,
            "key_topics": relevant_parts.key_topics if relevant_parts else None,
            "analysis_diagnostics": relevant_parts.diagnostics if relevant_parts else None,
            "ai_focus_tags": list(ai_focus_tags or []),
            "requested_transcription_provider": requested_transcription_provider,
            "effective_transcription_provider": effective_transcription_provider,
            "transcription_provider_resolution": provider_resolution,
        }

    @staticmethod
    async def render_video_segments(
        video_path: Path,
        segments: List[Dict[str, Any]],
        font_family: str = "TikTokSans-Regular",
        font_size: int = 24,
        font_color: str = "#FFFFFF",
        subtitle_style: Optional[Dict[str, Any]] = None,
        transitions_enabled: bool = False,
        progress_callback: Optional[callable] = None,
        cancel_check: Optional[Callable[[], Awaitable[None]]] = None,
        filename_prefix: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Render clips from prepared segments."""
        async def ensure_not_cancelled() -> None:
            if cancel_check:
                await cancel_check()

        await ensure_not_cancelled()

        if progress_callback:
            await progress_callback(
                70,
                "Creating video clips...",
                {"stage": "clips", "stage_progress": 0, "overall_progress": 70, "clip_index": 0, "clip_total": len(segments)},
            )

        clip_result = await VideoService.create_video_clips(
            video_path,
            segments,
            font_family,
            font_size,
            font_color,
            subtitle_style,
            transitions_enabled,
            progress_callback=progress_callback,
            filename_prefix=filename_prefix,
        )
        await ensure_not_cancelled()

        clips_info = clip_result.get("clips", [])
        clip_generation_diagnostics = clip_result.get("diagnostics", {})

        if progress_callback:
            await progress_callback(
                100,
                "Processing complete!",
                {"stage": "finalizing", "stage_progress": 100, "overall_progress": 100},
            )

        return {
            "clips": clips_info,
            "clip_generation_diagnostics": clip_generation_diagnostics,
        }

    @staticmethod
    async def process_video_complete(
        url: str,
        source_type: str,
        font_family: str = "TikTokSans-Regular",
        font_size: int = 24,
        font_color: str = "#FFFFFF",
        subtitle_style: Optional[Dict[str, Any]] = None,
        transitions_enabled: bool = False,
        transcription_provider: str = "local",
        assembly_api_key: Optional[str] = None,
        ai_provider: str = "openai",
        ai_api_key: Optional[str] = None,
        ai_base_url: Optional[str] = None,
        ai_api_key_fallbacks: Optional[List[str]] = None,
        ai_key_labels: Optional[List[str]] = None,
        ai_routing_mode: Optional[str] = None,
        ai_model: Optional[str] = None,
        ai_request_options: Optional[Dict[str, Any]] = None,
        transcription_options: Optional[Dict[str, Any]] = None,
        ai_focus_tags: Optional[List[str]] = None,
        default_framing_mode: str = "auto",
        face_detection_mode: str = "balanced",
        fallback_crop_position: str = "center",
        progress_callback: Optional[callable] = None,
        cancel_check: Optional[Callable[[], Awaitable[None]]] = None,
        filename_prefix: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Complete video processing pipeline.
        Returns dict with segments and clips info.
        """
        try:
            analysis_result = await VideoService.process_video_analysis(
                url=url,
                source_type=source_type,
                transcription_provider=transcription_provider,
                assembly_api_key=assembly_api_key,
                ai_provider=ai_provider,
                ai_api_key=ai_api_key,
                ai_base_url=ai_base_url,
                ai_api_key_fallbacks=ai_api_key_fallbacks,
                ai_key_labels=ai_key_labels,
                ai_routing_mode=ai_routing_mode,
                ai_model=ai_model,
                ai_request_options=ai_request_options,
                transcription_options=transcription_options,
                ai_focus_tags=ai_focus_tags,
                default_framing_mode=default_framing_mode,
                face_detection_mode=face_detection_mode,
                fallback_crop_position=fallback_crop_position,
                progress_callback=progress_callback,
                cancel_check=cancel_check,
            )

            render_result = await VideoService.render_video_segments(
                video_path=Path(analysis_result["video_path"]),
                segments=analysis_result["segments"],
                font_family=font_family,
                font_size=font_size,
                font_color=font_color,
                subtitle_style=subtitle_style,
                transitions_enabled=transitions_enabled,
                progress_callback=progress_callback,
                cancel_check=cancel_check,
                filename_prefix=filename_prefix,
            )

            return {
                "segments": analysis_result["segments"],
                "clips": render_result.get("clips", []),
                "summary": analysis_result.get("summary"),
                "key_topics": analysis_result.get("key_topics"),
                "ai_focus_tags": analysis_result.get("ai_focus_tags") or [],
                "analysis_diagnostics": analysis_result.get("analysis_diagnostics"),
                "clip_generation_diagnostics": render_result.get("clip_generation_diagnostics", {}),
                "video_path": analysis_result.get("video_path"),
            }
        except Exception as e:
            logger.error(f"Error in video processing pipeline: {e}")
            raise
