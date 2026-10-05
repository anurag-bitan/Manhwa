"""Smoke-test DeepSeek narration (run from repo root).

  .\\backend\\.venv\\Scripts\\python.exe scripts\\test_deepseek_narration.py
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND / ".env", override=False)

from core.config import settings  # noqa: E402
from core.deepseek_narration import chat_completions  # noqa: E402
from core.narration_prompt import NARRATION_SYSTEM  # noqa: E402


def main() -> int:
    if not settings.deepseek_api_key.strip():
        print("FAIL: DEEPSEEK_API_KEY is empty. Set it in backend/.env")
        return 1
    print(f"narration_backend={settings.narration_backend}")
    print(f"base_url={settings.deepseek_api_base_url}")
    print(f"model={settings.deepseek_model}")
    try:
        raw = chat_completions(
            [
                {"role": "system", "content": NARRATION_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        'Return JSON only: {"narrations": [{"segment_id": "scene_0000", '
                        '"scene_index": 0, "narration_text": "ok"}]}'
                    ),
                },
            ]
        )
        print(f"SUCCESS: response length={len(raw)}")
        print(raw[:400].encode("ascii", errors="backslashreplace").decode("ascii"))
        return 0
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
