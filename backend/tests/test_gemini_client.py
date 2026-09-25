import unittest
from unittest.mock import MagicMock, patch

from core.gemini_client import fetch_grounded_context, _truncate_words


class GeminiClientTests(unittest.TestCase):
    def test_truncate_words(self):
        text = " ".join(f"w{i}" for i in range(60))
        self.assertEqual(len(_truncate_words(text, 50).split()), 50)

    @patch("core.gemini_client._generate_with_search")
    def test_fetch_grounded_context_success(self, mock_search):
        mock_search.return_value = "A short grounded summary about the series."
        result = fetch_grounded_context("Solo Leveling")
        self.assertTrue(result["grounded"])
        self.assertGreater(result["word_count"], 0)

    def test_fetch_grounded_context_empty_name(self):
        result = fetch_grounded_context("")
        self.assertEqual(result["context"], "")


if __name__ == "__main__":
    unittest.main()
