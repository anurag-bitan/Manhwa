import logging

from core.config import settings
from core.pipeline_state import build_initial_pipeline_state
from db.supabase_admin import supabase_admin


logger = logging.getLogger(__name__)


def _load_queued_job(job_id: str) -> tuple[dict, dict]:
    response = (
        supabase_admin.table("processing_jobs")
        .select("id,status,pdf_storage_path,state_json")
        .eq("id", job_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        raise RuntimeError("Job not found")

    job = response.data[0]
    if job.get("status") == "TTS_COMPLETED":
        return job, job.get("state_json") or {}
    if job.get("status") != "QUEUED":
        raise RuntimeError(f"Job is not queued (status={job.get('status')})")

    state = job.get("state_json") or build_initial_pipeline_state(
        job_id,
        job["pdf_storage_path"],
    )
    state["job_id"] = job_id
    state["pdf_storage_path"] = job["pdf_storage_path"]
    return job, state


def _validate_stored_pdf(path: str) -> None:
    pdf_bytes = supabase_admin.storage.from_("pdfs").download(path)
    if len(pdf_bytes) > settings.max_pdf_bytes:
        raise ValueError(
            f"PDF is larger than the configured {settings.max_pdf_bytes // (1024 * 1024)} MB limit"
        )
    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("Uploaded object is not a valid PDF")


def process_queued_job(job_id: str) -> dict:
    """Validate and process one queued job. Intended as the Cloud Run Job entrypoint."""
    job, state = _load_queued_job(job_id)
    if job.get("status") == "TTS_COMPLETED":
        return state

    try:
        _validate_stored_pdf(job["pdf_storage_path"])
        state["status"] = "PROCESSING"
        state["error"] = None
        (
            supabase_admin.table("processing_jobs")
            .update({"status": "PROCESSING", "state_json": state})
            .eq("id", job_id)
            .eq("status", "QUEUED")
            .execute()
        )

        # Importing the OCR/LLM graph only inside the worker keeps the API image small.
        from core.langgraph_app import run_pipeline

        final_state = run_pipeline(state)
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
        logger.exception("Pipeline job %s failed", job_id)
        public_error = (
            str(exc)
            if isinstance(exc, ValueError)
            else "Processing failed. Please try a smaller PDF or try again later."
        )
        failed_state = {**state, "status": "FAILED", "error": public_error}
        (
            supabase_admin.table("processing_jobs")
            .update({"status": "FAILED", "state_json": failed_state})
            .eq("id", job_id)
            .execute()
        )
        raise
