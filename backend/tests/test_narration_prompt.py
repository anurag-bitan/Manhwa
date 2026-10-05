import unittest

from core.deepseek_narration import _chunk_scenes
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


class NarrationPromptTests(unittest.TestCase):
    def test_system_prompt_is_roman_hinglish_storyteller(self):
        lower = NARRATION_SYSTEM.lower()
        self.assertIn("roman hinglish", lower)
        self.assertIn("panel by panel", lower)

    def test_user_prompt_asks_for_continuous_story_and_word_cap(self):
        prompt = build_narration_user_prompt(
            title="Solo Leveling",
            chapter="Season 1, Chapter 1",
            series_context="A hunter grows stronger.",
            scene_lines=['- segment_id="scene_0000", scene_index=0, ocr="Sung Jinwoo is weak."'],
            remaining_words=600,
        )
        self.assertIn("continuous spoken story", prompt)
        self.assertIn("is panel mein", prompt)
        self.assertIn("600", prompt)
        self.assertIn("OCR", prompt)
        self.assertIn("scene_0000", prompt)

    def test_parse_keeps_stable_segment_ids(self):
        raw = '{"narrations": [{"segment_id": "scene_0002", "scene_index": 2, "narration_text": "Phir woh nikal pada."}]}'
        parsed = parse_narration_json(raw, ["scene_0002"])
        self.assertEqual(parsed["scene_0002"], "Phir woh nikal pada.")

    def test_full_chapter_scene_lines_stay_in_order(self):
        scenes = [
            {"segment_id": "scene_0000", "scene_index": 0, "text": "first"},
            {"segment_id": "scene_0001", "scene_index": 1, "text": "second"},
        ]
        lines = build_scene_lines(scenes)
        self.assertEqual(len(lines), 2)
        self.assertIn("scene_0000", lines[0])
        self.assertIn("scene_0001", lines[1])

    def test_word_cap_enforced(self):
        by_id = {
            "scene_0000": " ".join(["word"] * 400),
            "scene_0001": " ".join(["more"] * 400),
        }
        capped = cap_narration_words(by_id, ["scene_0000", "scene_0001"], max_words=600)
        total = count_words(assemble_story_summary(
            [{"narration_text": capped[sid]} for sid in ["scene_0000", "scene_0001"]]
        ))
        self.assertEqual(total, MAX_NARRATION_WORDS)
        self.assertEqual(count_words(capped["scene_0000"]), 400)
        self.assertEqual(count_words(capped["scene_0001"]), 200)

    def test_chunk_scenes_keeps_single_request_for_small_chapters(self):
        scenes = [
            {"segment_id": f"scene_{i:04d}", "scene_index": i, "text": "short"}
            for i in range(8)
        ]
        chunks = _chunk_scenes(scenes)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(len(chunks[0]), 8)


if __name__ == "__main__":
    unittest.main()
