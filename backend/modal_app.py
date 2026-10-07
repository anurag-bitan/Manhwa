"""Modal deployment: scale-to-zero API plus a single-concurrency OCR worker."""

from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

import modal


BACKEND_DIR = Path(__file__).resolve().parent
APP_NAME = "manhwa-video-backend"
SECRET_NAME = "manhwa-backend-secrets"
CONTAINER_APP_ROOT = "/app"
SOURCE_IGNORE = [
    ".env",
    ".env.*",
    "__pycache__",
    ".pytest_cache",
    "tests",
]


def flatten_requirements(path: Path) -> str:
    """Inline ``-r`` includes into one file.

    Modal copies only the path given to ``pip_install_from_requirements`` to
    ``/.requirements.txt``. Nested ``-r other.txt`` then looks for
    ``/other.txt`` and the image build fails.
    """
    lines: list[str] = []
    seen: set[Path] = set()

    def walk(current: Path) -> None:
        resolved = current.resolve()
        if resolved in seen:
            return
        if not resolved.is_file():
            raise FileNotFoundError(f"Requirements file not found: {resolved}")
        seen.add(resolved)
        for raw in resolved.read_text(encoding="utf-8").splitlines():
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("-r ") or stripped.startswith("--requirement "):
                included = stripped.split(maxsplit=1)[1]
                walk(resolved.parent / included)
                continue
            lines.append(stripped)

    walk(path)
    handle = NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix="modal-",
        suffix=f"-{path.name}",
        delete=False,
    )
    with handle:
        handle.write("\n".join(lines) + "\n")
    return handle.name

app = modal.App(APP_NAME)
backend_secret = modal.Secret.from_name(SECRET_NAME)


def _mount_backend(image: modal.Image) -> modal.Image:
    return (
        image.env({"PYTHONPATH": CONTAINER_APP_ROOT, "PYTHONUNBUFFERED": "1"})
        .workdir(CONTAINER_APP_ROOT)
        .add_local_dir(
            str(BACKEND_DIR),
            remote_path=CONTAINER_APP_ROOT,
            copy=True,
            ignore=SOURCE_IGNORE,
        )
    )


def _build_images() -> tuple[modal.Image, modal.Image]:
    # Imported only on the deploy machine. Runtime containers load this file
    # from /root without ocr_bootstrap on sys.path.
    from ocr_bootstrap import download_ocr_models

    api_image = _mount_backend(
        modal.Image.debian_slim(python_version="3.10")
        .pip_install_from_requirements(
            flatten_requirements(BACKEND_DIR / "requirements-api.txt")
        )
        .pip_install_from_requirements(
            flatten_requirements(BACKEND_DIR / "requirements-modal.txt")
        )
    )
    worker_image = _mount_backend(
        modal.Image.debian_slim(python_version="3.10")
        .apt_install(
            "libgomp1",
            "libglib2.0-0",
            "libsm6",
            "libxext6",
            "libxrender1",
            "libfontconfig1",
            "libjpeg62-turbo",
            "libpng16-16",
            "libgl1",
            "ffmpeg",
        )
        .pip_install_from_requirements(
            flatten_requirements(BACKEND_DIR / "requirements-worker.txt")
        )
        .add_local_file(
            str(BACKEND_DIR / "ocr_bootstrap.py"),
            remote_path="/root/ocr_bootstrap.py",
            copy=True,
        )
        .run_function(download_ocr_models)
    )
    return api_image, worker_image


if (BACKEND_DIR / "requirements-api.txt").is_file():
    api_image, worker_image = _build_images()
else:
    api_image = worker_image = modal.Image.debian_slim(python_version="3.10")


@app.function(
    image=api_image,
    secrets=[backend_secret],
    min_containers=0,
    max_containers=10,
    scaledown_window=60,
    timeout=300,
)
@modal.asgi_app()
def fastapi_app():
    from main import app as web_app

    return web_app


@app.function(
    name="process-job",
    image=worker_image,
    secrets=[backend_secret],
    cpu=2.0,
    memory=10240,
    timeout=7200,
    retries=0,
    min_containers=0,
    max_containers=1,
    scaledown_window=60,
)
@modal.concurrent(max_inputs=1)
def process_job(job_id: str) -> dict:
    from core.pipeline_runner import process_queued_job

    return process_queued_job(job_id, lease_owner=str(uuid4()))


@app.function(
    image=api_image,
    secrets=[backend_secret],
    schedule=modal.Period(minutes=5),
    min_containers=0,
    max_containers=1,
    timeout=300,
    retries=0,
)
def reconcile_stale_jobs() -> int:
    """Fail expired leases so a lost container never blocks the global queue."""
    from db.supabase_admin import supabase_admin

    response = supabase_admin.rpc("recover_stale_processing_jobs").execute()
    recovered = response.data or []
    return len(recovered)
