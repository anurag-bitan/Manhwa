"""Gemini API helpers for grounded context and batched narration."""

from __future__ import annotations

import io
import json
import logging
import re
from typing import Any

from google import genai
from google.genai import types
from PIL import Image

from core.config import settings


logger = logging.getLogger(__name__)

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is not None:
        return _client
    api_key = settings.gemini_api_key.strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY must be configured")
    _client = genai.Client(api_key=api_key)
    return _client


def _truncate_words(text: str, max_words: int = 50) -> str:
    words = text.split()
    return " ".join(words[:max_words])


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
    client = _get_client()
    config = types.GenerateContentConfig(
        temperature=0.2,
        max_output_tokens=200,
        tools=[types.Tool(google_search=types.GoogleSearch())],
    )
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=config,
    )
    return _response_text(response)


def _generate_plain_context(prompt: str) -> str:
    client = _get_client()
    config = types.GenerateContentConfig(
        temperature=0.2,
        max_output_tokens=200,
    )
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=config,
    )
    return _response_text(response)


def fetch_grounded_context(
    manhwa_name: str,
    *,
    season: str = "",
    chapter_number: str = "",
    genre: str = "",
) -> dict[str, Any]:
    """Return a short search-grounded blurb (max 50 words) without invented plot."""
    name = manhwa_name.strip()
    if not name:
        return {"context": "", "grounded": False, "word_count": 0}

    search_query = _build_search_query(
        name,
        season=season,
        chapter_number=chapter_number,
        genre=genre,
    )
    prompt = f"""You are summarizing a manhwa for a video narrator intro.

Search query: {search_query}

STRICT RULES:
- Use ONLY facts from Google Search results when search is available. Do not invent plot.
- Write at most 50 words.
- No spoilers beyond what search snippets mention.
- Do not invent character names, events, or chapters not present in search results.
- If you cannot ground the answer, respond with exactly: NO_GROUNDED_CONTEXT

Output only the summary text, no title, no bullet points."""

    raw = ""
    grounded = False
    try:
        raw = _generate_with_search(prompt)
        grounded = True
    except Exception:
        logger.warning(
            "Search-grounded context failed for %s; falling back to plain prompt",
            name,
            exc_info=True,
        )
        try:
            fallback_prompt = f"""Write at most 50 words describing the manhwa "{name}" for a narrator intro.
Use only widely known, non-spoiler premise information. If unsure, respond: NO_GROUNDED_CONTEXT
Output only the summary text."""
            raw = _generate_plain_context(fallback_prompt)
            grounded = False
        except Exception:
            logger.exception("Grounded context request failed for %s", name)
            return {"context": "", "grounded": False, "word_count": 0}

    if not raw or raw == "NO_GROUNDED_CONTEXT" or len(raw) < 10:
        return {"context": "", "grounded": False, "word_count": 0}

    context = _truncate_words(raw, 50)
    return {
        "context": context,
        "grounded": grounded,
        "word_count": len(context.split()),
    }


def panel_thumbnail_jpeg(page_bytes: bytes, bbox: list[int], max_size: int = 512) -> bytes:
    """Crop a panel from a page image and return a small JPEG for Gemini."""
    page_img = Image.open(io.BytesIO(page_bytes))
    x1, y1, x2, y2 = [int(v) for v in bbox]
    cropped = page_img.crop((x1, y1, x2, y2))
    cropped.thumbnail((max_size, max_size), Image.LANCZOS)
    buffer = io.BytesIO()
    cropped.convert("RGB").save(buffer, format="JPEG", quality=70)
    return buffer.getvalue()


def _parse_narration_json(raw: str, expected_ids: list[str]) -> dict[str, str]:
    cleaned = raw.strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)
    data = json.loads(cleaned)
    items = data.get("narrations", data if isinstance(data, list) else [])
    by_id: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        segment_id = str(item.get("segment_id", ""))
        text = str(item.get("narration_text", "")).strip()
        if segment_id:
            by_id[segment_id] = text
    for item in items:
        if not isinstance(item, dict):
            continue
        scene_index = item.get("scene_index")
        text = str(item.get("narration_text", "")).strip()
        if scene_index is not None and text:
            fallback_id = f"scene_{int(scene_index):04d}"
            if fallback_id in expected_ids and fallback_id not in by_id:
                by_id[fallback_id] = text
    return by_id


def generate_narration_batch(
    *,
    series_context: str,
    chapter_info: dict[str, Any],
    story_scenes: list[dict[str, Any]],
    panel_thumbnails: dict[str, bytes],
) -> dict[str, str]:
    """Generate Hindi narration for all story scenes in one (or chunked) Gemini call."""
    if not story_scenes:
        return {}

    client = _get_client()
    chapter = chapter_info.get("chapter", "")
    title = chapter_info.get("title", "")
    system_instruction = (
        "You are a Hindi YouTube storyteller narrating manhwa panels. "
        "Write energetic spoken Hindi. Use ONLY the provided OCR text and panel images. "
        "The series blurb is for intro grounding only—do not add plot beyond OCR/images. "
        "Never invent events, dialogue, or characters not visible in the panel. "
        "No stage directions or brackets."
    )

    all_results: dict[str, str] = {}
    batch_size = max(1, settings.narration_batch_size)

    for offset in range(0, len(story_scenes), batch_size):
        chunk = story_scenes[offset : offset + batch_size]
        scene_lines = []
        parts: list[types.Part] = []
        expected_ids: list[str] = []

        for scene in chunk:
            segment_id = scene["segment_id"]
            expected_ids.append(segment_id)
            ocr_text = scene.get("text", "")
            scene_lines.append(
                f'- segment_id="{segment_id}", scene_index={scene["scene_index"]}, '
                f'ocr="{ocr_text[:500]}"'
            )
            thumb = panel_thumbnails.get(segment_id)
            if thumb:
                parts.append(types.Part.from_bytes(data=thumb, mime_type="image/jpeg"))

        blurb = series_context.strip() or "No external context."
        prompt = f"""Generate Hindi narration for each story panel below.

Manhwa: {title}
Chapter: {chapter}
Series blurb (intro only, max 50 words, do not expand beyond OCR/images):
{blurb}

Panels (each needs 2-3 sentences of spoken Hindi based ONLY on its OCR and image):
{chr(10).join(scene_lines)}

Rules:
- First panel may weave one short intro sentence from the blurb if natural.
- Other panels: describe ONLY what is in that panel's OCR/image.
- Do not repeat previous panels.
- Skip adding narration for empty OCR with no visible story action.

Respond ONLY with JSON:
{{"narrations": [{{"segment_id": "...", "scene_index": 0, "narration_text": "..."}}]}}"""

        parts.insert(0, types.Part.from_text(text=prompt))
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.7,
            max_output_tokens=4096,
            response_mime_type="application/json",
        )
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=parts,
            config=config,
        )
        raw = _response_text(response)
        parsed = _parse_narration_json(raw, expected_ids)
        for segment_id in expected_ids:
            all_results[segment_id] = parsed.get(segment_id, "")

    return all_results
