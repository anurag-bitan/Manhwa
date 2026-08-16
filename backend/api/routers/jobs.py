from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID

from core.auth import AuthenticatedUser, get_current_user
from core.config import settings
from db.supabase_admin import supabase_admin

router = APIRouter(prefix="/jobs", tags=["jobs"])


def create_signed_asset_url(bucket: str, path: str) -> str:
    response = supabase_admin.storage.from_(bucket).create_signed_url(
        path,
        settings.storage_signed_url_ttl_seconds,
    )
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        signed_url = (
            response.get("signedURL")
            or response.get("signedUrl")
            or response.get("signed_url")
        )
        if signed_url:
            return signed_url
    raise HTTPException(status_code=500, detail="Could not authorize an asset URL")

@router.get("/{job_id}")
async def get_job_status(
    job_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    job = (
        supabase_admin.table("processing_jobs")
        .select("status,state_json")
        .eq("id", str(job_id))
        .eq("cognito_sub", current_user.sub)
        .execute()
    )
    if not job.data:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.data[0]

@router.get("/{job_id}/assets")
async def get_job_assets(
    job_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    job = (
        supabase_admin.table("processing_jobs")
        .select("state_json,status")
        .eq("id", str(job_id))
        .eq("cognito_sub", current_user.sub)
        .execute()
    )
    if not job.data:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.data[0].get("status") != "TTS_COMPLETED":
        raise HTTPException(status_code=409, detail="Job assets are not ready")
    if not job.data[0].get("state_json"):
        raise HTTPException(status_code=500, detail="Completed job assets are unavailable")
    state = job.data[0]["state_json"]

    scenes = state.get("scenes", [])
    page_urls = state.get("page_urls", [])
    audio_urls = state.get("audio_urls", [])
    timings = state.get("timings", [])
    panels = state.get("panels", [])
    combined_audio_path = state.get("combined_audio_path", "")
    combined_audio = (
        create_signed_asset_url("audio", combined_audio_path)
        if combined_audio_path
        else state.get("combined_audio_url", "")
    )
    narration = state.get("narration", [])

    # Build image list (page images)
    image_urls = [
        create_signed_asset_url("pages", page["path"])
        if page.get("path")
        else page.get("url", "")
        for page in page_urls
    ]

    timing_by_segment = {
        timing.get("segment_id"): timing
        for timing in timings
        if timing.get("segment_id")
    }
    audio_by_segment = {
        audio.get("segment_id"): (
            create_signed_asset_url("audio", audio["path"])
            if audio.get("path")
            else audio.get("url", "")
        )
        for audio in audio_urls
        if isinstance(audio, dict) and audio.get("segment_id")
    }

    # Build final_video_segments as expected by frontend
    final_video_segments = []
    for scene in scenes:
        if not scene.get("is_story"):
            continue
        idx = scene["scene_index"]
        segment_id = scene.get("segment_id", f"scene_{idx:04d}")
        # Find panel for this scene (each scene has one panel index)
        panel_idx = scene["panels"][0]
        panel = panels[panel_idx] if panel_idx < len(panels) else {}
        audio = audio_by_segment.get(segment_id, "")
        timing = timing_by_segment.get(segment_id)

        # Compatibility with jobs created before stable segment IDs existed.
        if timing is None:
            timing = next((t for t in timings if t.get("scene_index") == idx), None)
        if timing is None:
            timing = timings[idx] if idx < len(timings) else {"duration": 5}
        if not audio and idx < len(audio_urls) and isinstance(audio_urls[idx], str):
            audio = audio_urls[idx]

        start_time = timing.get("start_time", timing.get("start", 0))
        duration = timing.get("duration", 5)
        end_time = timing.get("end_time", start_time + duration)
        bbox = panel.get("bbox")
        animation_type = "zoom"
        if bbox and len(bbox) == 4:
            panel_width = max(1, bbox[2] - bbox[0])
            panel_height = max(1, bbox[3] - bbox[1])
            if panel_height > panel_width * 1.5:
                animation_type = "pan_down"
        narration_text = next(
            (
                item.get("narration_text", "")
                for item in narration
                if item.get("segment_id") == segment_id
                or item.get("scene_index") == idx
            ),
            "",
        )

        final_video_segments.append({
            "segment_id": segment_id,
            "narration_segment": narration_text,
            "image_page_index": panel.get("page_number", 0),  # index into image_urls
            "panel_index": panel_idx,
            "panel_bbox": bbox,
            "start_time": start_time,
            "end_time": end_time,
            "duration": duration,
            "animation_type": animation_type,
            "audio_url": audio,  # individual audio (optional, not used by videoMaker)
        })

    return {
        "image_urls": image_urls,
        "audio_url": combined_audio,          # single combined audio
        "final_video_segments": final_video_segments,
        "total_duration": sum(s["duration"] for s in final_video_segments),
    }
