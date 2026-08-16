from core.config import settings


class JobLaunchError(RuntimeError):
    """Raised when the API cannot submit a Cloud Run Job execution."""


def launch_cloud_run_job(job_id: str) -> str:
    """Start one private Cloud Run Job execution without waiting for completion."""
    job_resource = settings.cloud_run_job_resource
    if not job_resource:
        raise JobLaunchError(
            "GCP_PROJECT_ID, GCP_REGION, and CLOUD_RUN_JOB_NAME must be configured"
        )

    try:
        from google.cloud import run_v2

        override = run_v2.RunJobRequest.Overrides(
            container_overrides=[
                run_v2.RunJobRequest.Overrides.ContainerOverride(
                    env=[run_v2.EnvVar(name="JOB_ID", value=job_id)]
                )
            ],
            task_count=1,
            timeout=f"{settings.cloud_run_job_timeout_seconds}s",
        )
        request = run_v2.RunJobRequest(name=job_resource, overrides=override)
        operation = run_v2.JobsClient().run_job(request=request)
    except Exception as exc:
        raise JobLaunchError("Cloud Run Job submission failed") from exc

    underlying_operation = getattr(operation, "operation", None)
    return getattr(underlying_operation, "name", "") or "submitted"
