from typing import Any


def build_initial_pipeline_state(
    job_id: str,
    pdf_storage_path: str,
    *,
    manhwa_name: str = "",
    genre: str = "",
    chapter_number: str = "",
) -> dict[str, Any]:
    """Return the serializable state shared by the API and pipeline job."""
    return {
        "job_id": job_id,
        "pdf_storage_path": pdf_storage_path,
        "page_urls": [],
        "panels": [],
        "ocr_results": [],
        "status": "UPLOAD_PENDING",
        "series_context": "",
        "chapter_info": {},
        "story_summary": "",
        "scenes": [],
        "panel_descriptions": [],
        "rolling_summary": "",
        "narration": [],
        "audio_urls": [],
        "error": None,
        "manhwa_name": manhwa_name.strip(),
        "genre": genre.strip(),
        "chapter_number": chapter_number.strip(),
        "timings": [],
        "combined_audio_url": "",
        "combined_audio_path": "",
    }
