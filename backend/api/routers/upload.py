import asyncio
import logging
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, status
from pydantic import BaseModel, Field

from core.auth import AuthenticatedUser, get_current_user
from core.config import settings
from core.job_launcher import JobLaunchError, launch_cloud_run_job
from core.job_log import log_start, log_upload
from core.pipeline_state import build_initial_pipeline_state
from db.supabase_admin import supabase_admin


router = APIRouter(prefix="/jobs", tags=["jobs"])
logger = logging.getLogger(__name__)


class CreatePdfUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0)
    content_type: str = Field(default="application/pdf", max_length=100)
    manhwa_name: str = Field(default="", max_length=200)
    genre: str = Field(default="", max_length=100)
    season: str = Field(default="", max_length=50)
    chapter_number: str = Field(default="", max_length=50)
    series_context: str = Field(default="", max_length=12000)


class PageUploadUrlsRequest(BaseModel):
    page_count: int = Field(gt=0, le=200)


class StartJobBody(BaseModel):
    client_pages: bool = False
    page_count: int = Field(default=0, ge=0, le=200)


def _response_dict(response: object) -> dict:
    if isinstance(response, dict):
        return response
    if hasattr(response, "model_dump"):
        return response.model_dump()
    if hasattr(response, "dict"):
        return response.dict()
    return {}


def _signed_upload_token(response: object) -> str:
    data = _response_dict(response)
    token = data.get("token")
    if token:
        return str(token)

    signed_url = (
        data.get("signedURL")
        or data.get("signedUrl")
        or data.get("signed_url")
    )
    if signed_url:
        query_token = parse_qs(urlparse(str(signed_url)).query).get("token", [])
        if query_token:
            return query_token[0]
    raise RuntimeError("Supabase did not return a signed-upload token")


def _rpc_scalar(response: object) -> object:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return data[0] if data else ""
    return data


@router.post("/upload-url", status_code=status.HTTP_201_CREATED)
async def create_pdf_upload(
    request: CreatePdfUploadRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    filename = Path(request.filename).name
    if not filename.lower().endswith(".pdf"):
        logger.warning("upload rejected: not a .pdf filename=%s", filename)
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    if request.content_type.lower() not in {"application/pdf", "application/x-pdf"}:
        logger.warning(
            "upload rejected: bad content_type=%s filename=%s",
            request.content_type,
            filename,
        )
        raise HTTPException(status_code=400, detail="The file content type must be application/pdf")
    if request.size_bytes > settings.max_pdf_bytes:
        max_mb = settings.max_pdf_bytes // (1024 * 1024)
        logger.warning(
            "upload rejected: too large size_bytes=%s max_bytes=%s filename=%s",
            request.size_bytes,
            settings.max_pdf_bytes,
            filename,
        )
        raise HTTPException(status_code=413, detail=f"PDF must be {max_mb} MB or smaller")

    job_id = str(uuid4())
    file_path = f"{job_id}/source.pdf"
    log_upload(
        logger,
        job_id,
        "create_upload_url requested",
        user_sub=current_user.sub[:8] + "...",
        filename=filename,
        size_bytes=request.size_bytes,
        storage_path=file_path,
    )
    initial_state = build_initial_pipeline_state(
        job_id,
        file_path,
        manhwa_name=request.manhwa_name,
        genre=request.genre,
        season=request.season,
        chapter_number=request.chapter_number,
        series_context=request.series_context,
    )

    try:
        log_upload(logger, job_id, "supabase signed_upload_url")
        signed_response = supabase_admin.storage.from_("pdfs").create_signed_upload_url(
            file_path
        )
        upload_token = _signed_upload_token(signed_response)
        log_upload(logger, job_id, "supabase rpc create_processing_upload")
        creation_result = _rpc_scalar(supabase_admin.rpc(
            "create_processing_upload",
            {
                "p_job_id": job_id,
                "p_cognito_sub": current_user.sub,
                "p_pdf_storage_path": file_path,
                "p_state_json": initial_state,
                "p_max_pending_uploads": settings.max_pending_uploads_per_user,
                "p_max_pending_uploads_global": settings.max_pending_uploads_global,
            },
        ).execute())
    except Exception:
        logger.exception("[upload] job_id=%s phase=prepare failed", job_id)
        raise HTTPException(status_code=500, detail="Could not prepare the PDF upload")

    if creation_result in {"PENDING_LIMIT", "GLOBAL_PENDING_LIMIT"}:
        log_upload(logger, job_id, "quota blocked", rpc_result=creation_result)
        raise HTTPException(
            status_code=429,
            detail="Too many pending uploads. Finish or wait for an earlier upload to expire.",
        )
    if creation_result != "CREATED":
        logger.error(
            "[upload] job_id=%s phase=reserve unexpected rpc_result=%s",
            job_id,
            creation_result,
        )
        raise HTTPException(status_code=500, detail="Could not prepare the PDF upload")

    log_upload(
        logger,
        job_id,
        "ready for client PUT to storage",
        status="UPLOAD_PENDING",
        expires_in=7200,
    )
    return {
        "job_id": job_id,
        "path": file_path,
        "token": upload_token,
        "expires_in": 7200,
        "max_bytes": settings.max_pdf_bytes,
    }


@router.post("/{job_id}/page-upload-urls")
async def create_page_upload_urls(
    job_id: UUID,
    request: PageUploadUrlsRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    job_id_value = str(job_id)
    job = (
        supabase_admin.table("processing_jobs")
        .select("id,status,state_json")
        .eq("id", job_id_value)
        .eq("cognito_sub", current_user.sub)
        .limit(1)
        .execute()
    )
    if not job.data:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.data[0].get("status") != "UPLOAD_PENDING":
        raise HTTPException(status_code=409, detail="Pages can only be uploaded before processing starts")

    pages = []
    for page_num in range(request.page_count):
        file_path = f"{job_id_value}/pages/page_{page_num:04d}.jpg"
        signed_response = supabase_admin.storage.from_("pages").create_signed_upload_url(file_path)
        pages.append({
            "index": page_num,
            "path": file_path,
            "token": _signed_upload_token(signed_response),
        })
    log_upload(logger, job_id_value, "page signed upload urls", page_count=request.page_count)
    return {"job_id": job_id_value, "pages": pages, "expires_in": 7200}


@router.post("/{job_id}/start", status_code=status.HTTP_202_ACCEPTED)
async def start_job(
    job_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: AuthenticatedUser = Depends(get_current_user),
    body: StartJobBody = Body(default_factory=StartJobBody),
):
    job_id_value = str(job_id)
    log_start(
        logger,
        job_id_value,
        "start requested",
        user_sub=current_user.sub[:8] + "...",
        execution_mode=settings.pipeline_execution_mode,
    )
    reservation = supabase_admin.rpc(
        "queue_processing_job",
        {
            "p_job_id": job_id_value,
            "p_cognito_sub": current_user.sub,
            "p_max_user_starts_30d": settings.max_pipeline_starts_per_user_30d,
            "p_max_global_starts_30d": settings.max_pipeline_starts_global_30d,
        },
    ).execute()
    reservation_result = _rpc_scalar(reservation)
    log_start(logger, job_id_value, "queue_processing_job", rpc_result=reservation_result)

    if reservation_result == "NOT_FOUND":
        log_start(logger, job_id_value, "failed job not found")
        raise HTTPException(status_code=404, detail="Job not found")
    if reservation_result in {"BUSY", "USER_LIMIT", "GLOBAL_LIMIT"}:
        messages = {
            "BUSY": "Another pipeline job is running. Please try again later.",
            "USER_LIMIT": "Your 30-day processing limit has been reached.",
            "GLOBAL_LIMIT": "The service's 30-day processing limit has been reached.",
        }
        raise HTTPException(status_code=429, detail=messages[reservation_result])
    if isinstance(reservation_result, str) and reservation_result.startswith("ALREADY_"):
        current_status = reservation_result.removeprefix("ALREADY_")
        log_start(logger, job_id_value, "skipped already started", status=current_status)
        return {"job_id": job_id_value, "status": current_status, "already_started": True}
    if reservation_result != "QUEUED":
        log_start(
            logger,
            job_id_value,
            "failed invalid state for start",
            rpc_result=reservation_result,
        )
        raise HTTPException(status_code=409, detail="Job cannot be started in its current state")

    if body.client_pages and body.page_count > 0:
        row = (
            supabase_admin.table("processing_jobs")
            .select("state_json")
            .eq("id", job_id_value)
            .limit(1)
            .execute()
        )
        state_json = (row.data[0].get("state_json") if row.data else {}) or {}
        state_json["client_pages"] = True
        state_json["client_page_count"] = body.page_count
        supabase_admin.table("processing_jobs").update({"state_json": state_json}).eq(
            "id", job_id_value
        ).execute()
        log_start(logger, job_id_value, "client pages ready", page_count=body.page_count)

    execution_mode = settings.pipeline_execution_mode.strip().lower()
    try:
        if execution_mode == "local":
            from core.pipeline_runner import process_queued_job

            log_start(logger, job_id_value, "scheduling background pipeline (local)")
            background_tasks.add_task(process_queued_job, job_id_value)
        elif execution_mode == "cloud_run":
            log_start(logger, job_id_value, "launching Cloud Run job")
            await asyncio.to_thread(launch_cloud_run_job, job_id_value)
        else:
            raise JobLaunchError(
                "PIPELINE_EXECUTION_MODE must be either local or cloud_run"
            )
    except JobLaunchError:
        (
            supabase_admin.table("processing_jobs")
            .update({"status": "UPLOAD_PENDING", "started_at": None})
            .eq("id", job_id_value)
            .eq("status", "QUEUED")
            .execute()
        )
        logger.exception("[start] job_id=%s phase=launch failed", job_id_value)
        raise HTTPException(status_code=503, detail="Processing could not be started. Please retry.")

    log_start(logger, job_id_value, "accepted", status="QUEUED")
    return {"job_id": job_id_value, "status": "QUEUED", "already_started": False}
