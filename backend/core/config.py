from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    groq_api_key: str = "" 
    cognito_region: str = ""
    cognito_user_pool_id: str = ""
    cognito_app_client_id: str = ""
    cognito_issuer: str = ""
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    storage_signed_url_ttl_seconds: int = 7200
    max_pdf_bytes: int = 50 * 1024 * 1024
    pipeline_execution_mode: str = "local"
    gcp_project_id: str = ""
    gcp_region: str = ""
    cloud_run_job_name: str = "manhwa-pipeline"
    cloud_run_job_timeout_seconds: int = 7200
    max_pipeline_starts_per_user_30d: int = 3
    max_pipeline_starts_global_30d: int = 10
    max_pending_uploads_per_user: int = 2
    max_pending_uploads_global: int = 5

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip().rstrip("/")
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]

    @property
    def cloud_run_job_resource(self) -> str:
        if not self.gcp_project_id or not self.gcp_region or not self.cloud_run_job_name:
            return ""
        return (
            f"projects/{self.gcp_project_id}/locations/{self.gcp_region}"
            f"/jobs/{self.cloud_run_job_name}"
        )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "allow"

settings = Settings()
