"""
Helpers for optional AI clip-selection focus tags.
"""
from __future__ import annotations

from typing import Any, Iterable, List

MAX_AI_FOCUS_TAGS = 4

AI_FOCUS_TAGS: dict[str, dict[str, str]] = {
    "funny": {
        "label": "Funny",
        "prompt_hint": "Prioritize humor, punchlines, banter, absurdity, and moments likely to make viewers laugh.",
    },
    "clutch": {
        "label": "Clutch",
        "prompt_hint": "Prioritize close calls, saves, comebacks, high-skill recoveries, and last-second wins.",
    },
    "fails": {
        "label": "Fails",
        "prompt_hint": "Prioritize mistakes, misplays, awkward timing, whiffs, and entertaining things going wrong.",
    },
    "hype": {
        "label": "Hype",
        "prompt_hint": "Prioritize high-energy moments, celebrations, shouting, crowding, and strong excitement.",
    },
    "drama": {
        "label": "Drama",
        "prompt_hint": "Prioritize tension, conflict, arguments, betrayal, shock, and emotionally charged exchanges.",
    },
    "reactions": {
        "label": "Reactions",
        "prompt_hint": "Prioritize strong emotional reactions, surprise, disbelief, roasting, and memorable responses.",
    },
    "storytelling": {
        "label": "Storytelling",
        "prompt_hint": "Prioritize segments with a clear setup, progression, payoff, and complete narrative arc.",
    },
    "educational": {
        "label": "Educational",
        "prompt_hint": "Prioritize tips, explanations, teachable moments, and practical insights viewers can reuse.",
    },
    "wholesome": {
        "label": "Wholesome",
        "prompt_hint": "Prioritize kind, supportive, heartfelt, uplifting, and unexpectedly warm moments.",
    },
}


def normalize_ai_focus_tags(raw_tags: Any) -> List[str]:
    if raw_tags is None:
        return []
    if not isinstance(raw_tags, list):
        raise ValueError("ai_options.focus_tags must be an array of strings")

    normalized: List[str] = []
    seen: set[str] = set()
    for raw_tag in raw_tags:
        if not isinstance(raw_tag, str):
            raise ValueError("ai_options.focus_tags must contain only strings")
        tag = raw_tag.strip().lower()
        if not tag or tag not in AI_FOCUS_TAGS or tag in seen:
            continue
        seen.add(tag)
        normalized.append(tag)
        if len(normalized) >= MAX_AI_FOCUS_TAGS:
            break
    return normalized


def build_ai_focus_guidance(tags: Iterable[str]) -> str:
    normalized_tags = [tag for tag in tags if tag in AI_FOCUS_TAGS]
    if not normalized_tags:
        return ""

    lines = [
        "Editor focus tags:",
        "Treat these as soft ranking preferences, not hard requirements.",
        "If the transcript does not contain a strong match, still return the best generally strong clips.",
    ]
    for tag in normalized_tags:
        lines.append(f"- {tag}: {AI_FOCUS_TAGS[tag]['prompt_hint']}")
    return "\n".join(lines)
