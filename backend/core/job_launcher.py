import logging

from core.config import settings
from db.supabase_admin import supabase_admin


logger = logging.getLogger(__name__)


class JobLaunchError(RuntimeError):
    """Raised when the API cannot submit a detached worker."""


def launch_modal_job(job_id: str) -> str:
    """Spawn one detached Modal call and persist its operational call ID."""
    try:
        import modal

        worker = modal.Function.from_name(
            settings.modal_app_name,
            settings.modal_worker_function_name,
        )
        call = worker.spawn(job_id)
    except Exception as exc:
        raise JobLaunchError("Modal worker submission failed") from exc

    call_id = str(getattr(call, "object_id", "") or "")
    if not call_id:
        logger.warning("Modal spawn returned no call ID job_id=%s", job_id)
        call_id = "submitted"
    try:
        (
            supabase_admin.table("processing_jobs")
            .update({"modal_call_id": call_id})
            .eq("id", job_id)
            .execute()
        )
    except Exception:
        # The worker is already detached. Do not roll the job back and risk a
        # duplicate launch merely because operational metadata could not persist.
        logger.exception("Could not persist Modal call ID job_id=%s", job_id)
    return call_id
