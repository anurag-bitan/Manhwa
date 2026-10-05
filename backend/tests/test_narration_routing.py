import unittest

from core.config import Settings


class NarrationBackendTests(unittest.TestCase):
    def test_prefers_deepseek_when_key_set(self):
        s = Settings(deepseek_api_key="sk-test", narration_provider="")
        self.assertEqual(s.narration_backend, "deepseek")

    def test_explicit_gemini(self):
        s = Settings(deepseek_api_key="sk-test", narration_provider="gemini")
        self.assertEqual(s.narration_backend, "gemini")
