"""Shared narration prompts and JSON parsing."""

from __future__ import annotations

import json
import re

MAX_NARRATION_WORDS = 600
MAX_OCR_CHARS_PER_SCENE = 400
MAX_SINGLE_REQUEST_CHARS = 24000

NARRATION_SYSTEM = (
    "You are a human storyteller retelling a manhwa chapter in spoken Roman Hinglish "
    "(Hindi in Latin script, with natural English words). "
    "You already understood the whole chapter. Now tell it like a friend explaining the story, "
    "not like a chatbot and not like you are reading speech bubbles panel by panel. "
    "Use ONLY events present in the provided OCR. Series blurb is grounding only. "
    "Never invent plot, names, or twists that are not in the OCR. "
    "No stage directions, no brackets, no Devanagari."
)


def count_words(text: str) -> int:
    return len((text or "").split())


def assemble_story_summary(narrations: list[dict]) -> str:
    parts = [
        str(item.get("narration_text", "")).strip()
        for item in narrations
        if str(item.get("narration_text", "")).strip()
    ]
    return " ".join(parts).strip()


def cap_narration_words(
    by_id: dict[str, str],
    expected_ids: list[str],
    max_words: int = MAX_NARRATION_WORDS,
) -> dict[str, str]:
    total = 0
    capped: dict[str, str] = {}
    for segment_id in expected_ids:
        text = (by_id.get(segment_id) or "").strip()
        words = text.split()
        remaining = max_words - total
        if remaining <= 0:
            capped[segment_id] = ""
            continue
        if len(words) > remaining:
            capped[segment_id] = " ".join(words[:remaining]).strip()
            total = max_words
        else:
            capped[segment_id] = text
            total += len(words)
    return capped


def build_scene_lines(story_scenes: list[dict]) -> list[str]:
    lines: list[str] = []
    for scene in story_scenes:
        ocr = str(scene.get("text", "")).replace("\n", " ").strip()[:MAX_OCR_CHARS_PER_SCENE]
        lines.append(
            f'- segment_id="{scene["segment_id"]}", scene_index={scene["scene_index"]}, ocr="{ocr}"'
        )
    return lines


def build_narration_user_prompt(
    *,
    title: str,
    chapter: str,
    series_context: str,
    scene_lines: list[str],
    previous_story: str = "",
    remaining_words: int = MAX_NARRATION_WORDS,
) -> str:
    blurb = series_context.strip() or "No external context."
    prior = previous_story.strip()
    prior_block = (
        f"Story so far (continue from here, do not repeat):\n{prior}\n\n"
        if prior
        else ""
    )
    return f"""Retell this chapter as one continuous spoken story in Roman Hinglish.

Manhwa: {title}
Chapter: {chapter}
Series blurb (grounding only, do not add plot beyond OCR):
{blurb}

{prior_block}Story beats in order (OCR from the uploaded chapter):
{chr(10).join(scene_lines)}

How to write:
- Understand the full chapter first, then narrate like a human who got the story.
- Explain what is happening, why it matters, and how the mood shifts. Paraphrase dialogue.
- Do NOT describe panels one by one. Do NOT say "is panel mein" or read bubbles verbatim.
- Each segment_id is only a timing beat in the SAME story. Together they must read as one explanation.
- Keep the combined narration for this response under {max(40, remaining_words)} words.
- Skip empty beats that add no story.

Respond ONLY with JSON:
{{"narrations": [{{"segment_id": "...", "scene_index": 0, "narration_text": "..."}}]}}"""


def parse_narration_json(raw: str, expected_ids: list[str]) -> dict[str, str]:
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
