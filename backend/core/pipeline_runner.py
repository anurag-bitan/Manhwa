import logging

from core.deepseek_narration import DeepSeekError
from core.config import settings
from core.job_log import log_pipeline
from core.pipeline_state import build_initial_pipeline_state
from db.supabase_admin import supabase_admin


logger = logging.getLogger(__name__)


def _api_status_code(exc: BaseException) -> int | None:
    code = getattr(exc, "status_code", None)
    return code if isinstance(code, int) else None


def _load_queued_job(job_id: str) -> tuple[dict, dict]:
    log_pipeline(logger, job_id, "loading job row from Supabase")
    response = (
        supabase_admin.table("processing_jobs")
        .select("id,status,pdf_storage_path,state_json")
        .eq("id", job_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        log_pipeline(logger, job_id, "failed job not found in database")
        raise RuntimeError("Job not found")

    job = response.data[0]
    log_pipeline(
        logger,
        job_id,
        "job loaded",
        status=job.get("status"),
        pdf_storage_path=job.get("pdf_storage_path"),
    )
    if job.get("status") == "TTS_COMPLETED":
        return job, job.get("state_json") or {}
    if job.get("status") != "QUEUED":
        log_pipeline(logger, job_id, "failed unexpected status", status=job.get("status"))
        raise RuntimeError(f"Job is not queued (status={job.get('status')})")

    state = job.get("state_json") or build_initial_pipeline_state(
        job_id,
        job["pdf_storage_path"],
    )
    state["job_id"] = job_id
    state["pdf_storage_path"] = job["pdf_storage_path"]
    return job, state


def _validate_stored_pdf(job_id: str, path: str) -> None:
    log_pipeline(logger, job_id, "downloading PDF from storage", storage_path=path)
    try:
        pdf_bytes = supabase_admin.storage.from_("pdfs").download(path)
    except Exception:
        logger.exception(
            "[pipeline] job_id=%s phase=validate_pdf storage download failed path=%s",
            job_id,
            path,
        )
        raise ValueError(
            "PDF not found in storage. Upload may have failed before start was called."
        )
    size = len(pdf_bytes)
    log_pipeline(logger, job_id, "PDF downloaded", size_bytes=size)
    if size > settings.max_pdf_bytes:
        raise ValueError(
            f"PDF is larger than the configured {settings.max_pdf_bytes // (1024 * 1024)} MB limit"
        )
    if not pdf_bytes.startswith(b"%PDF-"):
        log_pipeline(
            logger,
            job_id,
            "invalid PDF header",
            first_bytes=pdf_bytes[:16].hex() if pdf_bytes else "empty",
        )
        raise ValueError("Uploaded object is not a valid PDF")
    log_pipeline(logger, job_id, "PDF header OK")


def process_queued_job(job_id: str) -> dict:
    """Validate and process one queued job. Intended as the Cloud Run Job entrypoint."""
    log_pipeline(logger, job_id, "background worker started")
    job, state = _load_queued_job(job_id)
    if job.get("status") == "TTS_COMPLETED":
        log_pipeline(logger, job_id, "already complete, skipping")
        return state

    try:
        _validate_stored_pdf(job_id, job["pdf_storage_path"])
        state["status"] = "PROCESSING"
        state["error"] = None
        log_pipeline(logger, job_id, "updating status", status="PROCESSING")
        (
            supabase_admin.table("processing_jobs")
            .update({"status": "PROCESSING", "state_json": state})
            .eq("id", job_id)
            .eq("status", "QUEUED")
            .execute()
        )

        # Importing the OCR/LLM graph only inside the worker keeps the API image small.
        from core.langgraph_app import run_pipeline

        log_pipeline(logger, job_id, "langgraph pipeline invoke")
        final_state = run_pipeline(state)
        log_pipeline(
            logger,
            job_id,
            "pipeline finished",
            final_status=final_state.get("status"),
            scenes=len(final_state.get("scenes") or []),
            narration_segments=len(final_state.get("narration") or []),
        )
        (
            supabase_admin.table("processing_jobs")
            .update({
                "status": final_state["status"],
                "state_json": final_state,
            })
            .eq("id", job_id)
            .execute()
        )
        return final_state
    except Exception as exc:

        logger.exception("[pipeline] job_id=%s phase=process failed error_type=%s", job_id, type(exc).__name__)
        if isinstance(exc, ValueError):
            public_error = str(exc)
        elif isinstance(exc, ModuleNotFoundError):
            public_error = (
                f"Pipeline dependency missing ({exc.name}). "
                "Local API needs the full worker stack: run `docker compose up --build` "
                "from backend/, or install requirements-worker.txt plus PaddleOCR."
            )
        elif isinstance(exc, DeepSeekError):
            public_error = str(exc)
        elif isinstance(exc, RuntimeError) and "GEMINI_API_KEY" in str(exc):
            public_error = str(exc)
        elif isinstance(exc, KeyError):
            public_error = f"Pipeline data error ({exc}). Please retry or contact support."
        elif _api_status_code(exc) == 503 or "high demand" in str(exc).lower():
            public_error = (
                "Gemini is temporarily overloaded (503). Wait a minute and upload again."
            )
        elif _api_status_code(exc) == 429:
            public_error = "Gemini rate limit hit (429). Wait a few minutes and try again."
        elif "ClientError" in type(exc).__name__ or "ServerError" in type(exc).__name__:
            public_error = (
                "AI model request failed. Confirm GEMINI_API_KEY and GEMINI_MODEL=gemini-3.8-flash "
                "in backend/.env, then rebuild Docker."
            )
        elif "genai" in type(exc).__module__:
            public_error = (
                "AI model request failed. Confirm GEMINI_API_KEY and GEMINI_MODEL=gemini-3.8-flash "
                "in backend/.env, then rebuild Docker."
            )
        else:
            public_error = "Processing failed. Please try a smaller PDF or try again later."
        failed_state = {**state, "status": "FAILED", "error": public_error}
        log_pipeline(
            logger,
            job_id,
            "persisting FAILED",
            public_error=public_error,
            last_pipeline_status=state.get("status"),
        )
        (
            supabase_admin.table("processing_jobs")
            .update({"status": "FAILED", "state_json": failed_state})
            .eq("id", job_id)
            .execute()
        )
        raise
