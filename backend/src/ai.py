"""
AI-related functions for transcript analysis with enhanced precision.
"""

from typing import List, Dict, Any, Optional, Tuple
import asyncio
import logging
import re

from pydantic_ai import Agent, NativeOutput
from pydantic import BaseModel, Field

from .ai_focus_tags import build_ai_focus_guidance
from .config import Config

logger = logging.getLogger(__name__)
config = Config()
SUPPORTED_AI_PROVIDERS = {"openai", "google", "anthropic", "zai", "ollama"}
DEFAULT_AI_MODELS = {
    "openai": "gpt-5-mini",
    "google": "gemini-2.5-pro",
    "anthropic": "claude-4-sonnet",
    "zai": "glm-5",
    "ollama": "gpt-oss:latest",
}
ZAI_OPENAI_BASE_URL = "https://api.z.ai/api/coding/paas/v4"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_NATIVE_OUTPUT_TEMPLATE = (
    "Return only valid JSON that matches this schema exactly. "
    "Do not include markdown code fences or any extra commentary.\n\n{schema}"
)
ANALYSIS_SINGLE_PASS_CHAR_THRESHOLD = 24_000
ANALYSIS_SINGLE_PASS_LINE_THRESHOLD = 180
ANALYSIS_CHUNK_MAX_CHARS = 16_000
ANALYSIS_CHUNK_MIN_LINES = 40
ANALYSIS_CHUNK_OVERLAP_LINES = 8
CHUNK_ANALYSIS_SEGMENT_TARGET = 8
GLOBAL_RERANK_MIN_CANDIDATES = 6
GLOBAL_RERANK_MAX_CANDIDATES = 40
TRANSCRIPT_LINE_RE = re.compile(r"^\[(?P<start>[^\]-]+?)\s*-\s*(?P<end>[^\]]+?)\]\s*(?P<text>.*)$")

class TranscriptSegment(BaseModel):
    """Represents a relevant segment of transcript with precise timing."""
    start_time: str = Field(description="Start timestamp in MM:SS format")
    end_time: str = Field(description="End timestamp in MM:SS format")
    text: str = Field(description="The transcript text for this segment")
    relevance_score: float = Field(description="Relevance score from 0.0 to 1.0", ge=0.0, le=1.0)
    reasoning: str = Field(description="Explanation for why this segment is relevant")

class TranscriptAnalysis(BaseModel):
    """Analysis result for transcript segments."""
    most_relevant_segments: List[TranscriptSegment]
    summary: str = Field(description="Brief summary of the video content")
    key_topics: List[str] = Field(description="List of main topics discussed")
    diagnostics: Dict[str, Any] = Field(default_factory=dict, description="Internal analysis diagnostics")


class RerankedCandidate(BaseModel):
    candidate_id: int = Field(description="Candidate identifier from the provided list", ge=1)
    relevance_score: float = Field(description="Updated global relevance score from 0.0 to 1.0", ge=0.0, le=1.0)
    reasoning: str = Field(description="Short reason for this ranking position")


class CandidateRerankResult(BaseModel):
    ranked_candidates: List[RerankedCandidate]


# Simplified system prompt that trusts transcript timing
simplified_system_prompt = """You are an expert at analyzing video transcripts to find the most engaging segments for short-form content creation.

CORE OBJECTIVES:
1. Identify segments that would be compelling on social media platforms
2. Focus on complete thoughts, insights, or entertaining moments
3. Prioritize content with hooks, emotional moments, or valuable information
4. Each segment should be engaging and worth watching

SEGMENT SELECTION CRITERIA:
1. STRONG HOOKS: Attention-grabbing opening lines
2. VALUABLE CONTENT: Tips, insights, interesting facts, stories
3. EMOTIONAL MOMENTS: Excitement, surprise, humor, inspiration
4. COMPLETE THOUGHTS: Self-contained ideas that make sense alone
5. ENTERTAINING: Content people would want to share

TIMING GUIDELINES:
- Segments MUST be between 10-45 seconds for optimal engagement
- CRITICAL: start_time MUST be different from end_time (minimum 10 seconds apart)
- Focus on natural content boundaries rather than arbitrary time limits
- Include enough context for the segment to be understandable
- IMPORTANT: candidate segments should be spread across the full video timeline when possible

TIMESTAMP REQUIREMENTS - EXTREMELY IMPORTANT:
- Use EXACT timestamps as they appear in the transcript
- Never modify timestamp format (keep MM:SS structure)
- start_time MUST be LESS THAN end_time (start_time < end_time)
- MINIMUM segment duration: 10 seconds (end_time - start_time >= 10 seconds)
- Look at transcript ranges like [02:25 - 02:35] and use different start/end times
- NEVER use the same timestamp for both start_time and end_time
- Example: start_time: "02:25", end_time: "02:35" (NOT "02:25" and "02:25")

Find 12-20 compelling candidate segments across the FULL timeline. Quality over quantity - choose segments that would genuinely engage viewers and have proper time ranges."""

global_rerank_system_prompt = """You are ranking pre-selected short-form clip candidates.

Rules:
1. Use ONLY candidate_id values provided by the user.
2. Return candidates in descending quality order for standalone short-form clips.
3. Score each returned candidate from 0.0 to 1.0 (higher is better).
4. Prefer strong hooks, complete thoughts, and social-shareability.
5. Do not invent IDs, timestamps, or text."""

def _parse_llm(value: str) -> Tuple[Optional[str], Optional[str]]:
    if ":" not in value:
        return None, value.strip() or None
    provider, model_name = value.split(":", 1)
    provider = provider.strip().lower()
    model_name = model_name.strip()
    return provider or None, model_name or None


def _default_ai_provider() -> str:
    configured_provider, _ = _parse_llm(config.llm or "")
    if configured_provider in SUPPORTED_AI_PROVIDERS:
        return configured_provider
    return "openai"


def _resolve_ai_model(ai_provider: str, requested_model: Optional[str]) -> str:
    if requested_model and requested_model.strip():
        return requested_model.strip()
    configured_provider, configured_model = _parse_llm(config.llm or "")
    if configured_provider == ai_provider and configured_model:
        return configured_model
    return DEFAULT_AI_MODELS[ai_provider]


def _normalize_base_url(value: Optional[str]) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw:
        return None
    if not raw.startswith(("http://", "https://")):
        raw = f"http://{raw}"
    return raw.rstrip("/")


def _resolve_ollama_openai_base_url(value: Optional[str]) -> str:
    resolved_base = _normalize_base_url(value) or _normalize_base_url(config.ollama_base_url) or DEFAULT_OLLAMA_BASE_URL
    if resolved_base.endswith("/v1"):
        return resolved_base
    return f"{resolved_base}/v1"


def _normalize_ollama_think(value: Any) -> Optional[Any]:
    if isinstance(value, bool):
        return value
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    if raw in {"false", "0", "no", "off"}:
        return False
    if raw in {"true", "1", "yes", "on"}:
        return True
    if raw in {"low", "medium", "high"}:
        return raw
    return None


def _default_ollama_think_for_model(model_name: str) -> Optional[Any]:
    normalized_model = str(model_name or "").strip().lower()
    if not normalized_model:
        return None
    if "qwen3" in normalized_model or "deepseek-r1" in normalized_model:
        return False
    if normalized_model.startswith("gpt-oss"):
        return "low"
    return None


def _parse_timestamp_to_seconds(raw_timestamp: str) -> Optional[float]:
    value = str(raw_timestamp or "").strip()
    if not value:
        return None

    parts = value.split(":")
    try:
        if len(parts) == 2:
            minute_text, second_text = parts
            if not minute_text.isdigit():
                return None
            seconds = float(second_text)
            if seconds < 0 or seconds >= 60:
                return None
            return int(minute_text) * 60 + seconds

        if len(parts) == 3:
            hour_text, minute_text, second_text = parts
            if not (hour_text.isdigit() and minute_text.isdigit()):
                return None
            minutes = int(minute_text)
            seconds = float(second_text)
            if minutes < 0 or minutes > 59 or seconds < 0 or seconds >= 60:
                return None
            return int(hour_text) * 3600 + minutes * 60 + seconds
    except ValueError:
        return None

    return None


def _normalize_segment_text(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _extract_transcript_lines(transcript: str) -> List[str]:
    return [line.strip() for line in str(transcript or "").splitlines() if line.strip()]


def _parse_formatted_transcript_line(line: str) -> Tuple[Optional[str], Optional[str]]:
    match = TRANSCRIPT_LINE_RE.match(str(line or "").strip())
    if not match:
        return None, None
    start = str(match.group("start") or "").strip()
    end = str(match.group("end") or "").strip()
    return (start or None), (end or None)


def _chunk_time_bounds(chunk_lines: List[str]) -> Tuple[Optional[str], Optional[str]]:
    start_time: Optional[str] = None
    end_time: Optional[str] = None

    for line in chunk_lines:
        start, _end = _parse_formatted_transcript_line(line)
        if start:
            start_time = start
            break

    for line in reversed(chunk_lines):
        _start, end = _parse_formatted_transcript_line(line)
        if end:
            end_time = end
            break

    return start_time, end_time


def _build_analysis_chunks(transcript: str) -> List[Dict[str, Any]]:
    lines = _extract_transcript_lines(transcript)
    if not lines:
        return [{
            "index": 1,
            "total": 1,
            "text": "",
            "line_count": 0,
            "char_count": 0,
            "start_time": None,
            "end_time": None,
            "start_line": 0,
            "end_line": 0,
        }]

    should_chunk = (
        len(transcript) > ANALYSIS_SINGLE_PASS_CHAR_THRESHOLD
        and len(lines) > ANALYSIS_SINGLE_PASS_LINE_THRESHOLD
    )
    if not should_chunk:
        start_time, end_time = _chunk_time_bounds(lines)
        return [{
            "index": 1,
            "total": 1,
            "text": "\n".join(lines),
            "line_count": len(lines),
            "char_count": len("\n".join(lines)),
            "start_time": start_time,
            "end_time": end_time,
            "start_line": 1,
            "end_line": len(lines),
        }]

    ranges: List[Tuple[int, int]] = []
    total_lines = len(lines)
    overlap = max(0, ANALYSIS_CHUNK_OVERLAP_LINES)
    start_index = 0
    while start_index < total_lines:
        char_count = 0
        end_index = start_index
        while end_index < total_lines:
            line_len = len(lines[end_index]) + 1
            projected_chars = char_count + line_len
            line_count = end_index - start_index
            if (
                line_count >= ANALYSIS_CHUNK_MIN_LINES
                and projected_chars > ANALYSIS_CHUNK_MAX_CHARS
            ):
                break
            char_count = projected_chars
            end_index += 1
            if (
                char_count >= ANALYSIS_CHUNK_MAX_CHARS
                and (end_index - start_index) >= ANALYSIS_CHUNK_MIN_LINES
            ):
                break

        if end_index <= start_index:
            end_index = min(total_lines, start_index + 1)

        ranges.append((start_index, end_index))
        if end_index >= total_lines:
            break
        next_start = end_index - overlap
        start_index = next_start if next_start > start_index else end_index

    chunks: List[Dict[str, Any]] = []
    total_chunks = len(ranges)
    for idx, (start_idx, end_idx) in enumerate(ranges, start=1):
        chunk_lines = lines[start_idx:end_idx]
        chunk_text = "\n".join(chunk_lines)
        start_time, end_time = _chunk_time_bounds(chunk_lines)
        chunks.append(
            {
                "index": idx,
                "total": total_chunks,
                "text": chunk_text,
                "line_count": len(chunk_lines),
                "char_count": len(chunk_text),
                "start_time": start_time,
                "end_time": end_time,
                "start_line": start_idx + 1,
                "end_line": end_idx,
            }
        )
    return chunks


def _build_analysis_prompt(
    transcript: str,
    *,
    chunk_metadata: Optional[Dict[str, Any]] = None,
    ai_focus_tags: Optional[List[str]] = None,
) -> str:
    focus_guidance = build_ai_focus_guidance(ai_focus_tags or [])
    focus_section = f"\n\n{focus_guidance}" if focus_guidance else ""
    if chunk_metadata and int(chunk_metadata.get("total") or 1) > 1:
        chunk_index = int(chunk_metadata.get("index") or 1)
        total_chunks = int(chunk_metadata.get("total") or 1)
        chunk_start = str(chunk_metadata.get("start_time") or "unknown")
        chunk_end = str(chunk_metadata.get("end_time") or "unknown")
        return f"""Analyze this transcript excerpt (chunk {chunk_index}/{total_chunks}) and identify the most engaging segments for short-form content.

This is only part of the full transcript. Focus on this excerpt's timeline window.
Return up to {CHUNK_ANALYSIS_SEGMENT_TARGET} high-quality candidate segments from this excerpt.

Excerpt window: {chunk_start} to {chunk_end}

Transcript excerpt:
{transcript}{focus_section}"""

    return f"""Analyze this video transcript and identify the most engaging segments for short-form content.

Find segments that would be compelling as standalone clips for social media.

Transcript:
{transcript}{focus_section}"""


def _dedupe_candidate_segments(segments: List[TranscriptSegment]) -> List[TranscriptSegment]:
    deduped: Dict[Tuple[str, str, str], TranscriptSegment] = {}
    for segment in segments:
        key = (
            str(segment.start_time or "").strip(),
            str(segment.end_time or "").strip(),
            _normalize_segment_text(segment.text),
        )
        existing = deduped.get(key)
        if existing is None or float(segment.relevance_score) > float(existing.relevance_score):
            deduped[key] = segment
    return list(deduped.values())


def _validate_analysis_segments(
    raw_segments: List[TranscriptSegment],
) -> Tuple[List[TranscriptSegment], Dict[str, int]]:
    validated_segments: List[TranscriptSegment] = []
    rejected_counts = {
        "insufficient_text": 0,
        "identical_timestamps": 0,
        "invalid_duration": 0,
        "too_short": 0,
        "invalid_timestamp_format": 0,
    }

    for segment in raw_segments:
        if not segment.text.strip() or len(segment.text.split()) < 3:
            logger.warning(f"Skipping segment with insufficient content: '{segment.text[:50]}...'")
            rejected_counts["insufficient_text"] += 1
            continue

        if segment.start_time == segment.end_time:
            logger.warning(f"Skipping segment with identical start/end times: {segment.start_time}")
            rejected_counts["identical_timestamps"] += 1
            continue

        start_seconds = _parse_timestamp_to_seconds(segment.start_time)
        end_seconds = _parse_timestamp_to_seconds(segment.end_time)
        if start_seconds is None or end_seconds is None:
            logger.warning(
                "Skipping segment with invalid timestamp format: %s-%s",
                segment.start_time,
                segment.end_time,
            )
            rejected_counts["invalid_timestamp_format"] += 1
            continue
        duration = end_seconds - start_seconds

        if duration <= 0:
            logger.warning(
                "Skipping segment with invalid duration: %s to %s = %ss",
                segment.start_time,
                segment.end_time,
                duration,
            )
            rejected_counts["invalid_duration"] += 1
            continue

        if duration < 5:
            logger.warning(f"Skipping segment too short: {duration}s (min 5s required)")
            rejected_counts["too_short"] += 1
            continue

        validated_segments.append(segment)
        logger.info(f"Validated segment: {segment.start_time}-{segment.end_time} ({duration:.1f}s)")

    validated_segments.sort(key=lambda x: x.relevance_score, reverse=True)
    return validated_segments, rejected_counts


def _combine_summaries(analyses: List[TranscriptAnalysis], chunk_count: int) -> str:
    summaries: List[str] = []
    for analysis in analyses:
        summary = str(analysis.summary or "").strip()
        if not summary:
            continue
        if summary in summaries:
            continue
        summaries.append(summary)

    if not summaries:
        if chunk_count > 1:
            return f"Aggregated analysis from {chunk_count} transcript chunks."
        return ""
    if len(summaries) == 1:
        return summaries[0]
    return " ".join(summaries[:3])


def _combine_key_topics(analyses: List[TranscriptAnalysis]) -> List[str]:
    deduped_topics: List[str] = []
    seen: set[str] = set()
    for analysis in analyses:
        for raw_topic in analysis.key_topics or []:
            topic = str(raw_topic or "").strip()
            if not topic:
                continue
            normalized = topic.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped_topics.append(topic)
    return deduped_topics


def _build_rerank_prompt(
    candidates_text: str,
    candidate_count: int,
    ai_focus_tags: Optional[List[str]] = None,
) -> str:
    focus_guidance = build_ai_focus_guidance(ai_focus_tags or [])
    focus_section = f"\n\n{focus_guidance}" if focus_guidance else ""
    return f"""Globally rank these clip candidates from best to worst.

Return exactly {candidate_count} entries in ranked_candidates, one per candidate_id, with no duplicates.
Every candidate_id from 1 to {candidate_count} must appear exactly once.

Candidates:
{candidates_text}{focus_section}"""


def _build_rerank_candidates_text(segments: List[TranscriptSegment]) -> str:
    lines: List[str] = []
    for idx, segment in enumerate(segments, start=1):
        text = " ".join(str(segment.text or "").split())
        if len(text) > 220:
            text = f"{text[:217]}..."
        lines.append(
            f"{idx}. [{segment.start_time} - {segment.end_time}] "
            f"score={float(segment.relevance_score):.3f} text=\"{text}\""
        )
    return "\n".join(lines)


async def _rerank_segments_globally(
    segments: List[TranscriptSegment],
    *,
    ai_provider: Optional[str] = None,
    ai_api_key: Optional[str] = None,
    ai_base_url: Optional[str] = None,
    ai_model: Optional[str] = None,
    ai_focus_tags: Optional[List[str]] = None,
    ai_request_options: Optional[Dict[str, Any]] = None,
    enabled: bool = True,
) -> Tuple[List[TranscriptSegment], Dict[str, Any]]:
    diagnostics: Dict[str, Any] = {
        "enabled": enabled,
        "attempted": False,
        "success": False,
        "input_candidates": len(segments),
        "max_candidates": GLOBAL_RERANK_MAX_CANDIDATES,
        "min_candidates": GLOBAL_RERANK_MIN_CANDIDATES,
    }
    if not enabled:
        diagnostics["reason"] = "disabled"
        return segments, diagnostics

    if len(segments) < GLOBAL_RERANK_MIN_CANDIDATES:
        diagnostics["reason"] = "insufficient_candidates"
        return segments, diagnostics

    candidate_segments = segments[:GLOBAL_RERANK_MAX_CANDIDATES]
    candidate_count = len(candidate_segments)
    diagnostics["attempted"] = True
    diagnostics["candidate_count"] = candidate_count
    logger.info("Starting global rerank pass for %s candidates", candidate_count)

    rerank_agent, resolved_provider, resolved_model = _build_rerank_agent(
        ai_provider=ai_provider,
        ai_api_key=ai_api_key,
        ai_base_url=ai_base_url,
        ai_model=ai_model,
        ai_request_options=ai_request_options,
    )
    diagnostics["provider"] = resolved_provider
    diagnostics["model"] = resolved_model

    candidates_text = _build_rerank_candidates_text(candidate_segments)
    prompt = _build_rerank_prompt(candidates_text, candidate_count, ai_focus_tags=ai_focus_tags)

    try:
        result = await rerank_agent.run(prompt)
        rerank = getattr(result, "data", None) or getattr(result, "output", None)
        if rerank is None:
            raise RuntimeError("Rerank result did not contain parsed output (expected .data or .output)")

        id_to_segment = {idx: segment for idx, segment in enumerate(candidate_segments, start=1)}
        ranked_segments: List[TranscriptSegment] = []
        seen_ids: set[int] = set()
        for ranked in rerank.ranked_candidates:
            candidate_id = int(ranked.candidate_id)
            segment = id_to_segment.get(candidate_id)
            if segment is None or candidate_id in seen_ids:
                continue
            ranked_segments.append(
                segment.model_copy(
                    update={
                        "relevance_score": float(ranked.relevance_score),
                        "reasoning": str(ranked.reasoning or "").strip() or str(segment.reasoning or ""),
                    }
                )
            )
            seen_ids.add(candidate_id)

        # Ensure no candidates are dropped even if rerank output is partial.
        for candidate_id, segment in id_to_segment.items():
            if candidate_id in seen_ids:
                continue
            ranked_segments.append(segment)

        reranked_output = ranked_segments + segments[GLOBAL_RERANK_MAX_CANDIDATES:]
        diagnostics["success"] = True
        diagnostics["returned_candidates"] = len(rerank.ranked_candidates)
        diagnostics["applied_candidates"] = len(ranked_segments)
        logger.info(
            "Global rerank pass complete: returned=%s applied=%s",
            diagnostics["returned_candidates"],
            diagnostics["applied_candidates"],
        )
        return reranked_output, diagnostics

    except Exception as exc:
        diagnostics["error"] = str(exc)
        diagnostics["error_type"] = type(exc).__name__
        logger.warning("Global rerank pass failed: %s", exc)
        return segments, diagnostics


def _select_diverse_segments(
    validated_segments: List[TranscriptSegment],
    max_clips: int,
    min_gap_seconds: float,
    bucket_count: int,
    enabled: bool,
) -> tuple[List[TranscriptSegment], Dict[str, Any]]:
    if not validated_segments:
        return [], {
            "enabled": enabled,
            "input_segments": 0,
            "selected_segments": 0,
        }

    safe_max_clips = max(1, int(max_clips))
    safe_min_gap = max(0.0, float(min_gap_seconds))
    candidates: List[Dict[str, Any]] = []
    for segment in validated_segments:
        start_seconds = _parse_timestamp_to_seconds(segment.start_time)
        end_seconds = _parse_timestamp_to_seconds(segment.end_time)
        if start_seconds is None or end_seconds is None:
            continue
        candidates.append(
            {
                "segment": segment,
                "start_seconds": start_seconds,
                "end_seconds": end_seconds,
                "bucket": 0,
            }
        )

    if not candidates:
        return [], {
            "enabled": enabled,
            "input_segments": len(validated_segments),
            "selected_segments": 0,
            "reason": "no_valid_timestamp_candidates",
        }

    candidates.sort(
        key=lambda item: (
            -float(item["segment"].relevance_score),
            float(item["start_seconds"]),
        )
    )

    if not enabled:
        selected = [item["segment"] for item in candidates[:safe_max_clips]]
        return selected, {
            "enabled": False,
            "input_segments": len(candidates),
            "selected_segments": len(selected),
            "max_clips": safe_max_clips,
            "min_gap_seconds": safe_min_gap,
            "bucket_count": max(1, int(bucket_count)),
        }

    timeline_start = min(float(item["start_seconds"]) for item in candidates)
    timeline_end = max(float(item["end_seconds"]) for item in candidates)
    timeline_span = max(0.0, timeline_end - timeline_start)
    safe_bucket_count = max(1, min(int(bucket_count), safe_max_clips, len(candidates)))
    if timeline_span > 0 and safe_max_clips > 1:
        safe_min_gap = min(safe_min_gap, timeline_span / float(safe_max_clips - 1))

    for item in candidates:
        if timeline_span <= 0 or safe_bucket_count == 1:
            item["bucket"] = 0
            continue
        position_ratio = (float(item["start_seconds"]) - timeline_start) / timeline_span
        item["bucket"] = min(
            safe_bucket_count - 1,
            max(0, int(position_ratio * safe_bucket_count)),
        )

    selected_indices: set[int] = set()
    selected_starts: List[float] = []

    def can_select(candidate_index: int, enforce_gap: bool = True) -> bool:
        if candidate_index in selected_indices:
            return False
        if len(selected_indices) >= safe_max_clips:
            return False
        if not enforce_gap or safe_min_gap <= 0:
            return True
        candidate_start = float(candidates[candidate_index]["start_seconds"])
        return all(abs(candidate_start - existing_start) >= safe_min_gap for existing_start in selected_starts)

    # First pass: try to guarantee timeline coverage (one high-score candidate per bucket).
    for bucket in range(safe_bucket_count):
        bucket_candidate_indices = [
            index for index, item in enumerate(candidates) if int(item["bucket"]) == bucket
        ]
        for candidate_index in bucket_candidate_indices:
            if can_select(candidate_index, enforce_gap=True):
                selected_indices.add(candidate_index)
                selected_starts.append(float(candidates[candidate_index]["start_seconds"]))
                break

    # Second pass: fill remaining slots by score while preserving gap.
    for candidate_index, _item in enumerate(candidates):
        if len(selected_indices) >= safe_max_clips:
            break
        if can_select(candidate_index, enforce_gap=True):
            selected_indices.add(candidate_index)
            selected_starts.append(float(candidates[candidate_index]["start_seconds"]))

    # Third pass: if gap rules block capacity, fill by score without gap enforcement.
    for candidate_index, _item in enumerate(candidates):
        if len(selected_indices) >= safe_max_clips:
            break
        if can_select(candidate_index, enforce_gap=False):
            selected_indices.add(candidate_index)
            selected_starts.append(float(candidates[candidate_index]["start_seconds"]))

    selected_items = sorted(
        (candidates[index] for index in selected_indices),
        key=lambda item: (
            -float(item["segment"].relevance_score),
            float(item["start_seconds"]),
        ),
    )
    selected_segments = [item["segment"] for item in selected_items]
    return selected_segments, {
        "enabled": True,
        "input_segments": len(candidates),
        "selected_segments": len(selected_segments),
        "max_clips": safe_max_clips,
        "min_gap_seconds": safe_min_gap,
        "bucket_count": safe_bucket_count,
        "timeline_start_seconds": timeline_start,
        "timeline_end_seconds": timeline_end,
        "timeline_span_seconds": timeline_span,
    }


def _build_ai_agent(
    *,
    output_type: Any,
    system_prompt: str,
    ai_provider: Optional[str] = None,
    ai_api_key: Optional[str] = None,
    ai_base_url: Optional[str] = None,
    ai_model: Optional[str] = None,
    ai_request_options: Optional[Dict[str, Any]] = None,
) -> tuple[Agent, str, str]:
    selected_provider = (ai_provider or _default_ai_provider()).strip().lower()
    if selected_provider not in SUPPORTED_AI_PROVIDERS:
        selected_provider = _default_ai_provider()

    selected_model = _resolve_ai_model(selected_provider, ai_model)
    resolved_key = (ai_api_key or "").strip()
    agent_output_type: Any = output_type
    agent_model_settings: Optional[Dict[str, Any]] = None

    if selected_provider == "openai":
        from pydantic_ai.models.openai import OpenAIModel
        from pydantic_ai.providers.openai import OpenAIProvider

        resolved_key = resolved_key or str(config.openai_api_key or "").strip()
        if not resolved_key:
            raise ValueError("OpenAI provider selected but no API key is configured")
        provider = OpenAIProvider(api_key=resolved_key)
        model = OpenAIModel(selected_model, provider=provider)
    elif selected_provider == "zai":
        from pydantic_ai.models.openai import OpenAIModel
        from pydantic_ai.providers.openai import OpenAIProvider

        resolved_key = resolved_key or str(config.zai_api_key or "").strip()
        if not resolved_key:
            raise ValueError("z.ai provider selected but no API key is configured")
        provider = OpenAIProvider(api_key=resolved_key, base_url=ZAI_OPENAI_BASE_URL)
        model = OpenAIModel(selected_model, provider=provider)
    elif selected_provider == "ollama":
        from pydantic_ai.models.openai import OpenAIModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from openai import AsyncOpenAI

        request_options = ai_request_options if isinstance(ai_request_options, dict) else {}
        auth_headers_raw = request_options.get("ollama_auth_headers")
        auth_headers: Dict[str, str] = {}
        if isinstance(auth_headers_raw, dict):
            for raw_key, raw_value in auth_headers_raw.items():
                header_key = str(raw_key or "").strip()
                header_value = str(raw_value or "").strip()
                if header_key and header_value:
                    auth_headers[header_key] = header_value
        timeout_override = request_options.get("ollama_timeout_seconds")
        max_retries_override = request_options.get("ollama_max_retries")
        temperature_override = request_options.get("ollama_temperature")
        think_override = _normalize_ollama_think(request_options.get("ollama_think"))

        timeout_value: float = 15.0
        if timeout_override is not None:
            try:
                timeout_value = float(timeout_override)
            except (TypeError, ValueError):
                timeout_value = 15.0
        timeout_value = max(1.0, min(600.0, timeout_value))

        max_retries_value: int = 2
        if max_retries_override is not None:
            try:
                max_retries_value = int(max_retries_override)
            except (TypeError, ValueError):
                max_retries_value = 2
        max_retries_value = max(0, min(10, max_retries_value))

        temperature_value: float = 0.0
        if temperature_override is not None:
            try:
                temperature_value = float(temperature_override)
            except (TypeError, ValueError):
                temperature_value = 0.0
        temperature_value = max(0.0, min(2.0, temperature_value))

        openai_client = AsyncOpenAI(
            api_key=resolved_key or "ollama",
            base_url=_resolve_ollama_openai_base_url(ai_base_url),
            timeout=timeout_value,
            max_retries=max_retries_value,
            default_headers=auth_headers or None,
        )
        provider = OpenAIProvider(
            openai_client=openai_client,
        )
        model = OpenAIModel(selected_model, provider=provider)
        # Ollama reliability improves when we force native JSON schema mode and deterministic decoding.
        agent_output_type = NativeOutput(
            output_type,
            strict=False,
            template=OLLAMA_NATIVE_OUTPUT_TEMPLATE,
        )
        think_value = (
            think_override
            if think_override is not None
            else _default_ollama_think_for_model(selected_model)
        )
        agent_model_settings = {
            "temperature": temperature_value,
        }
        if think_value is not None:
            agent_model_settings["extra_body"] = {"think": think_value}
    elif selected_provider == "google":
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google_gla import GoogleGLAProvider

        resolved_key = resolved_key or str(config.google_api_key or "").strip()
        if not resolved_key:
            raise ValueError("Google provider selected but no API key is configured")
        provider = GoogleGLAProvider(api_key=resolved_key)
        model = GoogleModel(selected_model, provider=provider)
    else:
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        resolved_key = resolved_key or str(config.anthropic_api_key or "").strip()
        if not resolved_key:
            raise ValueError("Anthropic provider selected but no API key is configured")
        provider = AnthropicProvider(api_key=resolved_key)
        model = AnthropicModel(selected_model, provider=provider)

    return (
        Agent(
            model=model,
            output_type=agent_output_type,
            system_prompt=system_prompt,
            model_settings=agent_model_settings,
        ),
        selected_provider,
        selected_model,
    )


def _build_transcript_agent(
    ai_provider: Optional[str] = None,
    ai_api_key: Optional[str] = None,
    ai_base_url: Optional[str] = None,
    ai_model: Optional[str] = None,
    ai_request_options: Optional[Dict[str, Any]] = None,
) -> tuple[Agent, str, str]:
    return _build_ai_agent(
        output_type=TranscriptAnalysis,
        system_prompt=simplified_system_prompt,
        ai_provider=ai_provider,
        ai_api_key=ai_api_key,
        ai_base_url=ai_base_url,
        ai_model=ai_model,
        ai_request_options=ai_request_options,
    )


def _build_rerank_agent(
    ai_provider: Optional[str] = None,
    ai_api_key: Optional[str] = None,
    ai_base_url: Optional[str] = None,
    ai_model: Optional[str] = None,
    ai_request_options: Optional[Dict[str, Any]] = None,
) -> tuple[Agent, str, str]:
    return _build_ai_agent(
        output_type=CandidateRerankResult,
        system_prompt=global_rerank_system_prompt,
        ai_provider=ai_provider,
        ai_api_key=ai_api_key,
        ai_base_url=ai_base_url,
        ai_model=ai_model,
        ai_request_options=ai_request_options,
    )

async def get_most_relevant_parts_by_transcript(
    transcript: str,
    ai_provider: Optional[str] = None,
    ai_api_key: Optional[str] = None,
    ai_base_url: Optional[str] = None,
    ai_model: Optional[str] = None,
    ai_focus_tags: Optional[List[str]] = None,
    ai_request_options: Optional[Dict[str, Any]] = None,
) -> TranscriptAnalysis:
    """Get the most relevant parts of a transcript for creating clips - simplified version."""
    transcript_agent, resolved_provider, resolved_model = _build_transcript_agent(
        ai_provider=ai_provider,
        ai_api_key=ai_api_key,
        ai_base_url=ai_base_url,
        ai_model=ai_model,
        ai_request_options=ai_request_options,
    )
    logger.info(
        "Starting AI analysis of transcript (%s chars) using provider=%s model=%s",
        len(transcript),
        resolved_provider,
        resolved_model,
    )

    try:
        chunks = _build_analysis_chunks(transcript)
        chunked_mode = len(chunks) > 1
        if chunked_mode:
            logger.info(
                "Chunked AI analysis enabled (%s chunks, max_chars=%s overlap_lines=%s)",
                len(chunks),
                ANALYSIS_CHUNK_MAX_CHARS,
                ANALYSIS_CHUNK_OVERLAP_LINES,
            )

        successful_analyses: List[TranscriptAnalysis] = []
        chunk_failures: List[Dict[str, Any]] = []
        chunk_results: List[Dict[str, Any]] = []

        for chunk in chunks:
            chunk_index = int(chunk.get("index") or 1)
            total_chunks = int(chunk.get("total") or 1)
            chunk_text = str(chunk.get("text") or "")
            if not chunk_text.strip():
                continue

            logger.info(
                "Analyzing transcript chunk %s/%s (%s chars, lines %s-%s)",
                chunk_index,
                total_chunks,
                chunk.get("char_count"),
                chunk.get("start_line"),
                chunk.get("end_line"),
            )
            prompt = _build_analysis_prompt(
                chunk_text,
                chunk_metadata=chunk if chunked_mode else None,
                ai_focus_tags=ai_focus_tags,
            )

            try:
                result = await transcript_agent.run(prompt)
                analysis = getattr(result, "data", None) or getattr(result, "output", None)
                if analysis is None:
                    raise RuntimeError("AI result did not contain parsed output (expected .data or .output)")
                successful_analyses.append(analysis)
                chunk_results.append(
                    {
                        "chunk_index": chunk_index,
                        "chunk_total": total_chunks,
                        "line_count": int(chunk.get("line_count") or 0),
                        "char_count": int(chunk.get("char_count") or 0),
                        "raw_segments": len(analysis.most_relevant_segments),
                        "start_time": chunk.get("start_time"),
                        "end_time": chunk.get("end_time"),
                    }
                )
                logger.info(
                    "AI analysis chunk %s/%s found %s segments",
                    chunk_index,
                    total_chunks,
                    len(analysis.most_relevant_segments),
                )
            except Exception as exc:
                logger.warning(
                    "AI analysis chunk %s/%s failed: %s",
                    chunk_index,
                    total_chunks,
                    exc,
                )
                chunk_failures.append(
                    {
                        "chunk_index": chunk_index,
                        "chunk_total": total_chunks,
                        "start_time": chunk.get("start_time"),
                        "end_time": chunk.get("end_time"),
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    }
                )

        if not successful_analyses:
            raise RuntimeError("AI analysis failed for all transcript chunks")

        raw_segments: List[TranscriptSegment] = []
        for analysis in successful_analyses:
            raw_segments.extend(analysis.most_relevant_segments)

        deduped_raw_segments = _dedupe_candidate_segments(raw_segments)
        validated_segments, rejected_counts = _validate_analysis_segments(deduped_raw_segments)
        reranked_segments, rerank_diagnostics = await _rerank_segments_globally(
            validated_segments,
            ai_provider=ai_provider,
            ai_api_key=ai_api_key,
            ai_base_url=ai_base_url,
            ai_model=ai_model,
            ai_focus_tags=ai_focus_tags,
            ai_request_options=ai_request_options,
            enabled=chunked_mode,
        )
        selected_segments, diversity_diagnostics = _select_diverse_segments(
            validated_segments=reranked_segments,
            max_clips=config.max_clips,
            min_gap_seconds=getattr(config, "clip_diversity_min_gap_seconds", 600),
            bucket_count=getattr(config, "clip_diversity_buckets", 4),
            enabled=bool(getattr(config, "clip_diversity_enabled", True)),
        )

        final_analysis = TranscriptAnalysis(
            most_relevant_segments=selected_segments,
            summary=_combine_summaries(successful_analyses, len(chunks)),
            key_topics=_combine_key_topics(successful_analyses),
            diagnostics={
                "raw_segments": len(raw_segments),
                "deduped_raw_segments": len(deduped_raw_segments),
                "validated_segments": len(validated_segments),
                "reranked_segments": len(reranked_segments),
                "selected_segments": len(selected_segments),
                "rejected_counts": rejected_counts,
                "rerank": rerank_diagnostics,
                "diversity": diversity_diagnostics,
                "analysis_chunks": {
                    "enabled": chunked_mode,
                    "requested_chunks": len(chunks),
                    "successful_chunks": len(successful_analyses),
                    "failed_chunks": len(chunk_failures),
                    "max_chars": ANALYSIS_CHUNK_MAX_CHARS,
                    "overlap_lines": ANALYSIS_CHUNK_OVERLAP_LINES,
                    "results": chunk_results,
                    "failures": chunk_failures,
                },
                "ai_focus_tags": list(ai_focus_tags or []),
            },
        )

        logger.info(f"Selected {len(selected_segments)} segments for processing")
        if selected_segments:
            logger.info(f"Top segment score: {selected_segments[0].relevance_score:.2f}")

        return final_analysis

    except Exception as e:
        logger.error(f"Error in transcript analysis: {e}")
        return TranscriptAnalysis(
            most_relevant_segments=[],
            summary=f"Analysis failed: {str(e)}",
            key_topics=[],
            diagnostics={
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )

def get_most_relevant_parts_sync(transcript: str) -> TranscriptAnalysis:
    """Synchronous wrapper for the async function."""
    return asyncio.run(get_most_relevant_parts_by_transcript(transcript))
