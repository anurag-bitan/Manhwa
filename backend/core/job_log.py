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
