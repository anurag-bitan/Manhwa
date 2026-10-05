"""Verify Supabase buckets, table, and upload RPC (run from repo root)."""
from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND / ".env", override=False)

from core.config import settings  # noqa: E402
from db.supabase_admin import supabase_admin  # noqa: E402


def main() -> int:
    if not settings.supabase_url.strip() or not settings.supabase_service_role_key.strip():
        print("FAIL: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing. Set them in backend/.env")
        return 1

    job_id = str(uuid4())
    verify_sub = f"verify-sub-{uuid4()}"
    path = f"{job_id}/source.pdf"
    errors: list[str] = []

    try:
        supabase_admin.storage.from_("pdfs").create_signed_upload_url(path)
    except Exception as exc:
        errors.append(f"pdfs bucket / signed upload: {exc}")

    try:
        supabase_admin.table("processing_jobs").select("id").limit(1).execute()
    except Exception as exc:
        errors.append(f"processing_jobs table: {exc}")

    try:
        response = supabase_admin.rpc(
            "create_processing_upload",
            {
                "p_job_id": job_id,
                "p_cognito_sub": verify_sub,
                "p_pdf_storage_path": path,
                "p_state_json": {"job_id": job_id},
                "p_max_pending_uploads": 2,
                "p_max_pending_uploads_global": 5,
            },
        ).execute()
        result = response.data
        if isinstance(result, list):
            result = result[0] if result else ""
        if result != "CREATED":
            errors.append(f"create_processing_upload returned: {result}")
        else:
            supabase_admin.table("processing_jobs").delete().eq("id", job_id).execute()
    except Exception as exc:
        errors.append(f"create_processing_upload RPC: {exc}")

    pending = (
        supabase_admin.table("processing_jobs")
        .select("id", count="exact")
        .eq("status", "UPLOAD_PENDING")
        .execute()
    )
    pending_count = pending.count if pending.count is not None else len(pending.data or [])
    if pending_count:
        print(
            f"Note: {pending_count} UPLOAD_PENDING job(s) from failed uploads. "
            "If the app says too many pending uploads, run in Supabase SQL Editor:"
        )
        print("  delete from public.processing_jobs where status = 'UPLOAD_PENDING';")

    if errors:
        print("VERIFY FAILED:")
        for err in errors:
            print(f" - {err}")
        return 1

    print("VERIFY OK: table, bucket, and RPC are ready for PDF uploads.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
