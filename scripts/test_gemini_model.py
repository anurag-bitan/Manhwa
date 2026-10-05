"""Smoke-test GEMINI_API_KEY + GEMINI_MODEL (run from repo root).

Tries the same model list as the API (primary + fallbacks).

Example:
  .\\backend\\.venv\\Scripts\\python.exe scripts\\test_gemini_model.py
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND / ".env", override=False)

from google import genai  # noqa: E402
from google.genai.errors import ClientError  # noqa: E402

from core.config import settings  # noqa: E402
from core.gemini_client import _model_candidates, _should_try_next_model  # noqa: E402


def main() -> int:
    if not settings.gemini_api_key:
        print("FAIL: GEMINI_API_KEY is empty. Set it in backend/.env")
        return 1

    candidates = _model_candidates()
    if not candidates:
        print("FAIL: GEMINI_MODEL is empty. Set it in backend/.env")
        return 1

    client = genai.Client(api_key=settings.gemini_api_key)
    last_error: Exception | None = None

    for model in candidates:
        if model.startswith("models/"):
            model = model.removeprefix("models/")
        print(f"Trying generate_content with model={model!r} ...")
        try:
            response = client.models.generate_content(
                model=model,
                contents="Reply with exactly one word: OK",
            )
            text = (response.text or "").strip()
            print(f"SUCCESS with {model}: {text[:200]}")
            if model != (settings.gemini_model or "").strip().removeprefix("models/"):
                print(
                    f"Tip: update backend/.env to GEMINI_MODEL={model} "
                    "(your configured primary model failed)."
                )
            return 0
        except ClientError as exc:
            if _should_try_next_model(exc):
                print(f"  skip: {exc}")
                last_error = exc
                continue
            print(f"FAIL: Gemini ClientError: {exc}")
            return 1
        except Exception as exc:
            print(f"FAIL: {type(exc).__name__}: {exc}")
            return 1

    print(f"FAIL: no model worked. Last error: {last_error}")
    print("Set GEMINI_MODEL=gemini-3.8-flash in backend/.env (see Google AI Studio model list).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
