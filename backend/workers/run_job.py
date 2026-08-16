import logging
import os

from core.pipeline_runner import process_queued_job


logging.basicConfig(level=logging.INFO)


def main() -> None:
    job_id = os.environ.get("JOB_ID", "").strip()
    if not job_id:
        raise RuntimeError("JOB_ID is required")
    process_queued_job(job_id)


if __name__ == "__main__":
    main()
