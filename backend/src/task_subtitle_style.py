"""Helpers for reconstructing and normalizing task subtitle_style payloads."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from .subtitle_style import normalize_subtitle_style

# Mapping of style keys to user default columns present on the joined task/user query.
USER_DEFAULT_STYLE_COLUMNS: Dict[str, str] = {
    "highlight_color": "default_highlight_color",
    "font_weight": "default_font_weight",
    "line_height": "default_line_height",
    "letter_spacing": "default_letter_spacing",
    "text_transform": "default_text_transform",
    "text_align": "default_text_align",
    "stroke_color": "default_stroke_color",
    "stroke_width": "default_stroke_width",
    "stroke_blur": "default_stroke_blur",
    "shadow_color": "default_shadow_color",
    "shadow_opacity": "default_shadow_opacity",
    "shadow_blur": "default_shadow_blur",
    "shadow_offset_x": "default_shadow_offset_x",
    "shadow_offset_y": "default_shadow_offset_y",
    "dim_unhighlighted": "default_dim_unhighlighted",
}


def build_normalized_subtitle_style_for_task(
    task_row: Mapping[str, Any],
    patch: Optional[Dict[str, Any]] = None,
    merge_with_existing: bool = True,
) -> Dict[str, Any]:
    """
    Build a normalized subtitle style for a task using available sources:
    1) existing task.subtitle_style (optional)
    2) user default style columns (as fallbacks)
    3) task font_family/font_size/font_color (authoritative for the task)
    4) optional patch payload (applied last)
    """
    seed: Dict[str, Any] = {}

    if merge_with_existing:
        existing_style = task_row.get("subtitle_style")
        if isinstance(existing_style, dict):
            seed.update(existing_style)

    for style_key, user_column in USER_DEFAULT_STYLE_COLUMNS.items():
        default_value = task_row.get(user_column)
        if default_value is not None:
            seed.setdefault(style_key, default_value)

    # Task-level font fields should override defaults when present.
    font_family = task_row.get("font_family")
    if isinstance(font_family, str) and font_family.strip():
        seed["font_family"] = font_family.strip()

    font_size = task_row.get("font_size")
    if font_size is not None:
        seed["font_size"] = font_size

    font_color = task_row.get("font_color")
    if isinstance(font_color, str) and font_color.strip():
        seed["font_color"] = font_color.strip()

    if patch:
        seed.update(patch)

    return normalize_subtitle_style(seed)
