"""Consistent log prefixes for PDF upload and processing (grep: [upload] [start] [pipeline])."""

from __future__ import annotations

import logging
from typing import Any


def _fmt_extra(extra: dict[str, Any]) -> str:
    if not extra:
        return ""
    return " " + " ".join(f"{key}={value}" for key, value in extra.items())


def log_upload(logger: logging.Logger, job_id: str, message: str, **extra: Any) -> None:
    logger.info("[upload] job_id=%s %s%s", job_id, message, _fmt_extra(extra))


def log_start(logger: logging.Logger, job_id: str, message: str, **extra: Any) -> None:
    logger.info("[start] job_id=%s %s%s", job_id, message, _fmt_extra(extra))


def log_pipeline(logger: logging.Logger, job_id: str, message: str, **extra: Any) -> None:
    logger.info("[pipeline] job_id=%s %s%s", job_id, message, _fmt_extra(extra))


def agent_debug_log(hypothesis_id: str, location: str, message: str, data: dict[str, Any]) -> None:
    # #region agent log
    try:
        import json
        import time
        from pathlib import Path

        docker_root = Path("/debug-logs")
        path = (
            docker_root / "debug-274e57.log"
            if docker_root.is_dir()
            else Path(__file__).resolve().parents[2] / "debug-274e57.log"
        )
        payload = {
            "sessionId": "274e57",
            "runId": "pre-fix",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, default=str) + "\n")
    except Exception:
        pass
    # #endregion
