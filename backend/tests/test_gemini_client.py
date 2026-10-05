import unittest
from unittest.mock import patch

from core.gemini_client import (
    _truncate_words,
    context_word_limit,
    fetch_grounded_context,
)


class GeminiClientTests(unittest.TestCase):
    def test_truncate_words(self):
        text = " ".join(f"w{i}" for i in range(60))
        self.assertEqual(len(_truncate_words(text, 50).split()), 50)

    def test_word_limit_grows_with_season_and_chapter(self):
        self.assertEqual(context_word_limit(), 250)
        self.assertEqual(context_word_limit(season="1"), 400)
        self.assertEqual(context_word_limit(season="1", chapter_number="5"), 600)

    @patch("core.deepseek_narration.fetch_context_deepseek")
    @patch("core.gemini_client._generate_with_search")
    def test_fetch_grounded_context_uses_gemini_if_deepseek_empty(self, mock_search, mock_deepseek):
        mock_deepseek.return_value = {"context": "", "grounded": False, "word_count": 0}
        mock_search.return_value = " ".join(["word"] * 40)
        result = fetch_grounded_context("Solo Leveling")
        self.assertTrue(result["grounded"])
        self.assertEqual(result["word_count"], 40)

    @patch("core.deepseek_narration.fetch_context_deepseek")
    @patch("core.gemini_client._generate_with_search")
    def test_deepseek_first_when_usable(self, mock_search, mock_deepseek):
        mock_deepseek.return_value = {
            "context": " ".join(["plot"] * 30),
            "grounded": False,
            "word_count": 30,
        }
        result = fetch_grounded_context("Solo Leveling", season="1", chapter_number="1")
        mock_search.assert_not_called()
        self.assertEqual(result["word_count"], 30)

    def test_fetch_grounded_context_empty_name(self):
        result = fetch_grounded_context("")
        self.assertEqual(result["context"], "")


if __name__ == "__main__":
    unittest.main()
