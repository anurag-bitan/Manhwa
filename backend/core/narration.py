"""Route narration to DeepSeek (default) or Gemini."""

from __future__ import annotations

import logging
from typing import Any

from core.config import settings
from core.deepseek_narration import generate_narration_batch_deepseek
from core.gemini_client import generate_narration_batch_gemini

logger = logging.getLogger(__name__)


def generate_narration_batch(
    *,
    series_context: str,
    chapter_info: dict[str, Any],
    story_scenes: list[dict[str, Any]],
    panel_thumbnails: dict[str, bytes],
) -> dict[str, str]:
    backend = settings.narration_backend
    logger.info("[pipeline] narration backend=%s", backend)
    if backend == "gemini":
        return generate_narration_batch_gemini(
            series_context=series_context,
            chapter_info=chapter_info,
            story_scenes=story_scenes,
            panel_thumbnails=panel_thumbnails,
        )
    return generate_narration_batch_deepseek(
        series_context=series_context,
        chapter_info=chapter_info,
        story_scenes=story_scenes,
        panel_thumbnails=panel_thumbnails,
    )
