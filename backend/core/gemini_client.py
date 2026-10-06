"""Gemini API helpers for grounded context and batched narration."""

from __future__ import annotations

import io
import json
import logging
import re
from typing import Any

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError
from PIL import Image

from core.config import settings
from core.narration_prompt import (
    MAX_NARRATION_WORDS,
    NARRATION_SYSTEM,
    assemble_story_summary,
    build_narration_user_prompt,
    build_scene_lines,
    cap_narration_words,
    count_words,
    parse_narration_json,
)


logger = logging.getLogger(__name__)

_client: genai.Client | None = None

# Used when GEMINI_MODEL is retired or unavailable for the API key.
_GEMINI_MODEL_FALLBACKS: tuple[str, ...] = (
    "gemini-3.8-flash",
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite",
)


def _model_candidates() -> list[str]:
    primary = settings.gemini_model.strip()
    ordered: list[str] = []
    if primary:
        ordered.append(primary)
    for model in _GEMINI_MODEL_FALLBACKS:
        if model not in ordered:
            ordered.append(model)
    return ordered


def _is_model_not_found(exc: Exception) -> bool:
    if isinstance(exc, ClientError) and getattr(exc, "status_code", None) == 404:
        return True
    message = str(exc).lower()
    return "not_found" in message or "no longer available" in message


def _api_status_code(exc: Exception) -> int | None:
    code = getattr(exc, "status_code", None)
    if isinstance(code, int):
        return code
    message = str(exc)
    if "429" in message or "RESOURCE_EXHAUSTED" in message:
        return 429
    if "503" in message or "UNAVAILABLE" in message:
        return 503
    if "404" in message or "NOT_FOUND" in message:
        return 404
    return None


def _should_try_next_model(exc: Exception) -> bool:
    if _is_model_not_found(exc):
        return True
    status = _api_status_code(exc)
    if status in {429, 503}:
        return True
    message = str(exc).lower()
    if "high demand" in message or "unavailable" in message:
        return True
    if "bidiGenerateContent" in message or "gemini live api" in message:
        return True
    if "only supports real-time" in message:
        return True
    return False


def _generate_content(*, contents: Any, config: types.GenerateContentConfig | None = None):
    client = _get_client()
    last_error: Exception | None = None
    for model in _model_candidates():
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
            logger.info("[pipeline] gemini generate_content ok model=%s", model)
            return response
        except (ClientError, ServerError) as exc:
            if _should_try_next_model(exc):
                logger.warning(
                    "Gemini model %s failed (status=%s), trying next model",
                    model,
                    _api_status_code(exc),
                )
                last_error = exc
                if _api_status_code(exc) == 429:
                    break
                continue
            raise
        except Exception as exc:
            if _should_try_next_model(exc):
                logger.warning("Gemini model %s unavailable for generate_content, trying next", model)
                last_error = exc
                continue
            raise
    if last_error:
        raise last_error
    raise RuntimeError("No Gemini model configured")


def _get_client() -> genai.Client:
    global _client
    if _client is not None:
        return _client
    api_key = settings.gemini_api_key.strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY must be configured")
    _client = genai.Client(api_key=api_key)
    return _client


def _truncate_words(text: str, max_words: int = 600) -> str:
    words = text.split()
    return " ".join(words[:max_words])


def context_word_limit(*, season: str = "", chapter_number: str = "") -> int:
    if (chapter_number or "").strip():
        return 600
    if (season or "").strip():
        return 400
    return 250


def _response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if text:
        return str(text).strip()
    candidates = getattr(response, "candidates", None) or []
    if candidates:
        content = getattr(candidates[0], "content", None)
        parts = getattr(content, "parts", None) or []
        chunks: list[str] = []
        for part in parts:
            part_text = getattr(part, "text", None)
            if part_text:
                chunks.append(str(part_text))
        return "".join(chunks).strip()
    return ""


def _build_search_query(
    manhwa_name: str,
    *,
    season: str = "",
    chapter_number: str = "",
    genre: str = "",
) -> str:
    name = manhwa_name.strip()
    if season and chapter_number:
        return f"{name} manhwa season {season.strip()} chapter {chapter_number.strip()} synopsis"
    if chapter_number:
        return f"{name} manhwa chapter {chapter_number.strip()} synopsis"
    if season:
        return f"{name} manhwa season {season.strip()} premise"
    if genre:
        return f"{name} {genre.strip()} manhwa premise"
    return f"{name} manhwa premise"


def _generate_with_search(prompt: str) -> str:
    config = types.GenerateContentConfig(
        temperature=0.3,
        max_output_tokens=4096,
        tools=[types.Tool(google_search=types.GoogleSearch())],
    )
    response = _generate_content(contents=prompt, config=config)
    return _response_text(response)


def _generate_plain_context(prompt: str) -> str:
    config = types.GenerateContentConfig(
        temperature=0.3,
        max_output_tokens=2048,
    )
    response = _generate_content(contents=prompt, config=config)
    return _response_text(response)


def _context_prompt(
    search_query: str,
    *,
    name: str,
    season: str,
    chapter_number: str,
    max_words: int,
    require_search: bool,
) -> str:
    focus = "the overall series premise"
    if season and chapter_number:
        focus = f"season {season.strip()} chapter {chapter_number.strip()} — a full chapter recap"
    elif chapter_number:
        focus = f"chapter {chapter_number.strip()} — a full chapter recap"
    elif season:
        focus = f"season {season.strip()} — a season recap"
    search_rule = (
        "Use Google Search / public web results. If trained knowledge is incomplete, search the web and write from those results."
        if require_search
        else "Use widely known published plot. If you are not sure, respond with exactly: NO_GROUNDED_CONTEXT"
    )
    return f"""Write a complete story context for a manhwa narrator.

Title: {name}
Focus: {focus}
Search query: {search_query}

RULES:
- {search_rule}
- Write a flowing summary, not bullet points, up to {max_words} words. Finish sentences.
- Cover setup, main characters, and what happens in the requested season/chapter when those are given.
- Do not invent names, fights, or twists that are not in search results or well-known published plot.
- If you cannot find reliable information, respond with exactly: NO_GROUNDED_CONTEXT

Output only the summary text."""


def _usable_context(raw: str) -> bool:
    text = (raw or "").strip()
    if not text or text == "NO_GROUNDED_CONTEXT":
        return False
    return len(text.split()) >= 20


def fetch_gemini_context(
    manhwa_name: str,
    *,
    season: str = "",
    chapter_number: str = "",
    genre: str = "",
) -> dict[str, Any]:
    """Gemini Google Search, then Gemini knowledge. No DeepSeek."""
    name = manhwa_name.strip()
    if not name:
        return {"context": "", "grounded": False, "word_count": 0}

    max_words = context_word_limit(season=season, chapter_number=chapter_number)
    search_query = _build_search_query(
        name,
        season=season,
        chapter_number=chapter_number,
        genre=genre,
    )
    prompt = _context_prompt(
        search_query,
        name=name,
        season=season,
        chapter_number=chapter_number,
        max_words=max_words,
        require_search=True,
    )

    raw = ""
    grounded = False
    try:
        raw = _generate_with_search(prompt)
        grounded = _usable_context(raw)
    except Exception:
        logger.warning("Gemini search context failed for %s", name, exc_info=True)

    if not _usable_context(raw):
        try:
            fallback_prompt = _context_prompt(
                search_query,
                name=name,
                season=season,
                chapter_number=chapter_number,
                max_words=max_words,
                require_search=False,
            )
            raw = _generate_plain_context(fallback_prompt)
            grounded = False
        except Exception:
            logger.exception("Gemini plain context failed for %s", name)
            return {"context": "", "grounded": False, "word_count": 0}

    if not _usable_context(raw):
        return {"context": "", "grounded": False, "word_count": 0}

    context = _truncate_words(raw, max_words)
    return {
        "context": context,
        "grounded": grounded,
        "word_count": len(context.split()),
    }


def fetch_grounded_context(
    manhwa_name: str,
    *,
    season: str = "",
    chapter_number: str = "",
    genre: str = "",
) -> dict[str, Any]:
    """Series/chapter context: DeepSeek first, then Gemini search/knowledge."""
    if not manhwa_name.strip():
        return {"context": "", "grounded": False, "word_count": 0}

    from core.deepseek_narration import fetch_context_deepseek

    max_words = context_word_limit(season=season, chapter_number=chapter_number)
    ds = fetch_context_deepseek(
        manhwa_name,
        season=season,
        chapter_number=chapter_number,
        genre=genre,
        max_words=max_words,
    )
    if _usable_context(ds.get("context", "")):
        return ds

    result = fetch_gemini_context(
        manhwa_name,
        season=season,
        chapter_number=chapter_number,
        genre=genre,
    )
    if _usable_context(result.get("context", "")):
        return result

    logger.warning("Gemini context empty after DeepSeek miss")
    return ds


def panel_thumbnail_jpeg(page_bytes: bytes, bbox: list[int], max_size: int = 256) -> bytes:
    """Crop a panel from a page image and return a small JPEG for Gemini."""
    page_img = Image.open(io.BytesIO(page_bytes))
    x1, y1, x2, y2 = [int(v) for v in bbox]
    cropped = page_img.crop((x1, y1, x2, y2))
    cropped.thumbnail((max_size, max_size), Image.LANCZOS)
    buffer = io.BytesIO()
    cropped.convert("RGB").save(buffer, format="JPEG", quality=40, optimize=True)
    return buffer.getvalue()


def generate_narration_batch_gemini(
    *,
    series_context: str,
    chapter_info: dict[str, Any],
    story_scenes: list[dict[str, Any]],
    panel_thumbnails: dict[str, bytes],
) -> dict[str, str]:
    """Generate Hindi narration for all story scenes in one (or chunked) Gemini call."""
    if not story_scenes:
        logger.info("[pipeline] gemini narration skipped (no story scenes)")
        return {}

    logger.info(
        "[pipeline] gemini narration start story_scenes=%s batch_size=%s model_primary=%s",
        len(story_scenes),
        settings.narration_batch_size,
        settings.gemini_model,
    )

    chapter = chapter_info.get("chapter", "")
    title = chapter_info.get("title", "")
    system_instruction = NARRATION_SYSTEM

    all_results: dict[str, str] = {}
    expected_all = [scene["segment_id"] for scene in story_scenes]
    batch_size = max(len(story_scenes), 1)
    previous_story = ""
    used_words = 0

    for offset in range(0, len(story_scenes), batch_size):
        chunk = story_scenes[offset : offset + batch_size]
        remaining = max(40, MAX_NARRATION_WORDS - used_words)
        logger.info(
            "[pipeline] gemini narration batch offset=%s count=%s remaining_words=%s",
            offset,
            len(chunk),
            remaining,
        )
        parts: list[types.Part] = []
        expected_ids: list[str] = []

        for scene in chunk:
            segment_id = scene["segment_id"]
            expected_ids.append(segment_id)
            thumb = panel_thumbnails.get(segment_id)
            if thumb:
                parts.append(types.Part.from_bytes(data=thumb, mime_type="image/jpeg"))

        prompt = build_narration_user_prompt(
            title=title,
            chapter=chapter,
            series_context=series_context,
            scene_lines=build_scene_lines(chunk),
            previous_story=previous_story,
            remaining_words=remaining,
        )

        parts.insert(0, types.Part.from_text(text=prompt))
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.75,
            max_output_tokens=4096,
            response_mime_type="application/json",
        )
        response = _generate_content(contents=parts, config=config)
        raw = _response_text(response)
        try:
            parsed = parse_narration_json(raw, expected_ids)
        except Exception:
            logger.exception(
                "[pipeline] gemini narration JSON parse failed offset=%s raw_len=%s",
                offset,
                len(raw),
            )
            raise
        filled = sum(1 for segment_id in expected_ids if parsed.get(segment_id, "").strip())
        logger.info(
            "[pipeline] gemini narration batch done offset=%s filled=%s/%s",
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

    return cap_narration_words(all_results, expected_all)
