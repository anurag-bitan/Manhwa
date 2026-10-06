"""Hindi narration via DeepSeek OpenAI-compatible chat completions (text/OCR only)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from core.config import settings
from core.narration_prompt import (
    MAX_NARRATION_WORDS,
    MAX_SINGLE_REQUEST_CHARS,
    NARRATION_SYSTEM,
    assemble_story_summary,
    build_narration_user_prompt,
    build_scene_lines,
    cap_narration_words,
    count_words,
    parse_narration_json,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE = "https://api.deepseek.com"


class DeepSeekError(RuntimeError):
    """DeepSeek request failed."""


def _base_url() -> str:
    return settings.deepseek_api_base_url.strip().rstrip("/") or DEFAULT_BASE


def chat_completions(messages: list[dict[str, Any]]) -> str:
    api_key = settings.deepseek_api_key.strip()
    if not api_key:
        raise DeepSeekError("DEEPSEEK_API_KEY is not set in backend/.env")

    url = f"{_base_url()}/chat/completions"
    payload = {
        "model": settings.deepseek_model,
        "messages": messages,
        "temperature": 0.75,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    logger.info("[pipeline] deepseek request model=%s url=%s", settings.deepseek_model, url)
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        logger.error("[pipeline] deepseek HTTP %s: %s", exc.code, detail)
        raise DeepSeekError(f"DeepSeek HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise DeepSeekError(f"DeepSeek network error: {exc.reason}") from exc

    try:
        return str(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise DeepSeekError(f"Unexpected DeepSeek response: {data!r}") from exc


def fetch_context_deepseek(
    manhwa_name: str,
    *,
    season: str = "",
    chapter_number: str = "",
    genre: str = "",
    max_words: int = 600,
) -> dict[str, Any]:
    """Knowledge fallback when Gemini search/context fails."""
    name = manhwa_name.strip()
    if not name:
        return {"context": "", "grounded": False, "word_count": 0}
    if not settings.deepseek_api_key.strip():
        return {"context": "", "grounded": False, "word_count": 0}

    focus = "the overall series premise and main plot"
    if season.strip() and chapter_number.strip():
        focus = f"season {season.strip()} chapter {chapter_number.strip()} as a full recap"
    elif chapter_number.strip():
        focus = f"chapter {chapter_number.strip()} as a full recap"
    elif season.strip():
        focus = f"season {season.strip()} as a recap"
    genre_bit = f" Genre: {genre.strip()}." if genre.strip() else ""

    prompt = f"""Write a complete story context for "{name}".{genre_bit}
Focus on {focus}.
Write 150 to {max_words} flowing words (not bullets) from well-known published plot.
If the exact chapter title is unclear, still summarize the main series and that chapter/season from public knowledge.
Never reply with a refusal token. Output only the summary text."""
    try:
        raw = chat_completions(
            [
                {
                    "role": "system",
                    "content": "You summarize manhwa plots from public knowledge. Prefer a full recap over saying you do not know.",
                },
                {"role": "user", "content": prompt},
            ]
        )
    except DeepSeekError:
        logger.exception("[context] deepseek fallback failed for %s", name)
        return {"context": "", "grounded": False, "word_count": 0}

    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1].strip()
    words = len(text.split())
    if "NO_GROUNDED_CONTEXT" in text and words < 40:
        text = text.replace("NO_GROUNDED_CONTEXT", "").strip()
        words = len(text.split())
    if not text or words < 12:
        return {"context": "", "grounded": False, "word_count": 0}
    clipped = text.split()[:max_words]
    context = " ".join(clipped)
    return {"context": context, "grounded": False, "word_count": len(clipped)}


def _chunk_scenes(story_scenes: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    total_chars = sum(len(str(scene.get("text", ""))) for scene in story_scenes)
    if total_chars <= MAX_SINGLE_REQUEST_CHARS:
        return [story_scenes]
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    used = 0
    for scene in story_scenes:
        scene_chars = min(len(str(scene.get("text", ""))), 400) + 80
        if current and used + scene_chars > MAX_SINGLE_REQUEST_CHARS:
            chunks.append(current)
            current = []
            used = 0
        current.append(scene)
        used += scene_chars
    if current:
        chunks.append(current)
    return chunks


def generate_narration_batch_deepseek(
    *,
    series_context: str,
    chapter_info: dict[str, Any],
    story_scenes: list[dict[str, Any]],
    panel_thumbnails: dict[str, bytes],
) -> dict[str, str]:
    del panel_thumbnails  # text-only: skip image upload so narration stays fast
    if not story_scenes:
        logger.info("[pipeline] deepseek narration skipped (no story scenes)")
        return {}

    chapter = chapter_info.get("chapter", "")
    title = chapter_info.get("title", "")
    all_results: dict[str, str] = {}
    expected_all = [scene["segment_id"] for scene in story_scenes]
    chunks = _chunk_scenes(story_scenes)
    logger.info(
        "[pipeline] deepseek narration start story_scenes=%s chunks=%s model=%s",
        len(story_scenes),
        len(chunks),
        settings.deepseek_model,
    )

    previous_story = ""
    used_words = 0
    for offset, chunk in enumerate(chunks):
        remaining = max(40, MAX_NARRATION_WORDS - used_words)
        expected_ids = [scene["segment_id"] for scene in chunk]
        prompt = build_narration_user_prompt(
            title=title,
            chapter=chapter,
            series_context=series_context,
            scene_lines=build_scene_lines(chunk),
            previous_story=previous_story,
            remaining_words=remaining,
        )
        logger.info(
            "[pipeline] deepseek narration chunk=%s count=%s remaining_words=%s",
            offset,
            len(chunk),
            remaining,
        )
        raw = chat_completions(
            [
                {"role": "system", "content": NARRATION_SYSTEM},
                {"role": "user", "content": prompt},
            ]
        )
        try:
            parsed = parse_narration_json(raw, expected_ids)
        except Exception:
            logger.exception(
                "[pipeline] deepseek JSON parse failed chunk=%s raw_len=%s",
                offset,
                len(raw),
            )
            raise
        filled = sum(1 for sid in expected_ids if parsed.get(sid, "").strip())
        logger.info(
            "[pipeline] deepseek chunk done offset=%s filled=%s/%s",
            offset,
            filled,
            len(expected_ids),
        )
        for segment_id in expected_ids:
            all_results[segment_id] = parsed.get(segment_id, "")
        previous_story = assemble_story_summary(
            [{"narration_text": all_results[sid]} for sid in expected_all if all_results.get(sid)]
        )
        used_words = count_words(previous_story)
        if used_words >= MAX_NARRATION_WORDS:
            break

    capped = cap_narration_words(all_results, expected_all)
    logger.info(
        "[pipeline] deepseek narration total_words=%s",
        count_words(assemble_story_summary(
            [{"narration_text": capped.get(sid, "")} for sid in expected_all]
        )),
    )
    return capped
