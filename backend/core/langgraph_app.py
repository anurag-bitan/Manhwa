from langgraph.graph import StateGraph, END
from typing import TypedDict, List, Optional, Callable
from db.supabase_admin import supabase_admin
import asyncio
import logging
import re
import io
import time
from functools import wraps

from core.narration_prompt import assemble_story_summary

logger = logging.getLogger(__name__)

class PipelineState(TypedDict):
    job_id: str
    pdf_storage_path: str
    page_urls: List[dict]
    panels: List[dict]
    ocr_results: List[dict]
    status: str
    series_context: str
    chapter_info: dict
    story_summary: str
    scenes: List[dict]
    panel_descriptions: List[str]
    rolling_summary: str
    narration: List[dict]
    error: Optional[str]
    audio_urls: List[dict]
    combined_audio_path: str
    combined_audio_url: str
    timings: List[dict]
    manhwa_name: str
    genre: str
    season: str
    chapter_number: str

def extract_pages_node(state: PipelineState) -> PipelineState:
    from workers.tasks import extract_pages

    page_urls = extract_pages(state["pdf_storage_path"], state["job_id"])
    state["page_urls"] = page_urls
    state["status"] = "EXTRACTED"
    update_job_status(state["job_id"], state["status"])
    return state

def detect_panels_node(state: PipelineState) -> PipelineState:
    from workers.tasks import detect_panels

    panels_all = [
        detect_panels(page["path"], i)
        for i, page in enumerate(state["page_urls"])
    ]

    all_panels = []
    for page_data in panels_all:
        page_num = page_data["page_number"]
        page_path = state["page_urls"][page_num]["path"]
        boxes = page_data["boxes"]

        if len(boxes) == 0:
            all_panels.append({
                "page_number": page_num,
                "bbox": [0, 0, 1200, 1600],
                "page_path": page_path
            })
        else:
            for box in boxes:
                all_panels.append({
                    "page_number": page_num,
                    "bbox": box,
                    "page_path": page_path
                })

    state["panels"] = all_panels
    state["status"] = "PANELS_DETECTED"
    update_job_status(state["job_id"], state["status"])
    return state


def update_job_status(job_id: str, status: str):
    try:
        supabase_admin.table("processing_jobs").update({"status": status}).eq("id", job_id).execute()
        logger.debug("[pipeline] job_id=%s db status=%s", job_id, status)
    except Exception:
        logger.exception("[pipeline] job_id=%s failed to update status=%s", job_id, status)


def _node_result_summary(node_name: str, state: PipelineState) -> str:
    if node_name == "extract_pages":
        return f"pages={len(state.get('page_urls') or [])}"
    if node_name == "detect_panels":
        return f"panels={len(state.get('panels') or [])}"
    if node_name == "crop_and_ocr":
        return f"ocr_results={len(state.get('ocr_results') or [])}"
    if node_name == "build_scenes":
        scenes = state.get("scenes") or []
        story = sum(1 for s in scenes if s.get("is_story"))
        return f"scenes={len(scenes)} story_scenes={story}"
    if node_name == "generate_narration":
        narr = state.get("narration") or []
        with_text = sum(1 for n in narr if (n.get("narration_text") or "").strip())
        return f"narration_segments={len(narr)} with_text={with_text}"
    if node_name == "synthesize_audio":
        return (
            f"audio_clips={len(state.get('audio_urls') or [])} "
            f"combined={'yes' if state.get('combined_audio_path') else 'no'}"
        )
    return f"status={state.get('status')}"


def _wrap_pipeline_node(node_name: str, fn: Callable[[PipelineState], PipelineState]):
    @wraps(fn)
    def wrapper(state: PipelineState) -> PipelineState:
        job_id = state.get("job_id", "unknown")
        logger.info("[pipeline] job_id=%s node=%s event=start", job_id, node_name)
        started = time.perf_counter()
        try:
            new_state = fn(state)
            elapsed = time.perf_counter() - started
            logger.info(
                "[pipeline] job_id=%s node=%s event=done elapsed_sec=%.2f %s",
                job_id,
                node_name,
                elapsed,
                _node_result_summary(node_name, new_state),
            )
            return new_state
        except Exception:
            elapsed = time.perf_counter() - started
            logger.exception(
                "[pipeline] job_id=%s node=%s event=failed elapsed_sec=%.2f",
                job_id,
                node_name,
                elapsed,
            )
            raise

    return wrapper


def crop_and_ocr_node(state: PipelineState) -> PipelineState:
    from workers.tasks import crop_and_ocr

    ocr_results = [
        crop_and_ocr(panel, idx)
        for idx, panel in enumerate(state["panels"])
    ]

    ocr_results.sort(key=lambda x: x["panel_index"])
    state["ocr_results"] = ocr_results
    state["status"] = "OCR_COMPLETED"
    update_job_status(state["job_id"], state["status"])
    return state


def apply_chapter_metadata_node(state: PipelineState) -> PipelineState:
    """Set chapter metadata from user input. Series context comes from upload preview."""
    title = (state.get("manhwa_name") or "").strip() or "Unknown"
    chapter_num = (state.get("chapter_number") or "").strip()
    season = (state.get("season") or "").strip()

    chapter_label = f"Chapter {chapter_num}" if chapter_num else "Chapter ?"
    if season:
        chapter_label = f"Season {season}, {chapter_label}"

    state["chapter_info"] = {
        "title": title,
        "chapter": chapter_label,
        "season": season,
        "is_correct": bool(chapter_num),
    }
    if not state.get("series_context"):
        state["series_context"] = ""

    state["status"] = "CHAPTER_DETECTED"
    update_job_status(state["job_id"], state["status"])
    return state


def build_scenes_node(state: PipelineState) -> PipelineState:
    SKIP_KEYWORDS = [
        "author", "note", "credit", "disclaimer", "support the official",
        "read this from the official", "free release", "patreon",
        "help us release faster", "more content better quality",
        "artist", "editor", "scanlation", "typeset", "proofread",
        "do not repost", "do not redistribute", "fan translation",
        "this is a fan translation", "unofficial", "non profit",
        "to be continued"
    ]

    scenes = []
    story_index = 0
    for i, ocr in enumerate(state["ocr_results"]):
        text = ocr["text"].lower()
        is_skip = any(keyword in text for keyword in SKIP_KEYWORDS)
        if not text.strip() or text in ["", "44^^^44||"]:
            is_skip = True
        if is_skip:
            scenes.append({
                "scene_index": i,
                "segment_id": f"scene_{i:04d}",
                "panels": [ocr["panel_index"]],
                "text": ocr["text"],
                "is_story": False
            })
        else:
            scenes.append({
                "scene_index": i,
                "story_index": story_index,
                "segment_id": f"scene_{i:04d}",
                "panels": [ocr["panel_index"]],
                "text": ocr["text"],
                "is_story": True
            })
            story_index += 1

    state["scenes"] = scenes
    state["rolling_summary"] = ""
    state["status"] = "SCENE_BUILDING"
    update_job_status(state["job_id"], state["status"])
    return state


def _build_panel_thumbnails(state: PipelineState, story_scenes: list[dict]) -> dict[str, bytes]:
    from core.gemini_client import panel_thumbnail_jpeg

    page_cache: dict[str, bytes] = {}
    thumbnails: dict[str, bytes] = {}

    for scene in story_scenes:
        segment_id = scene["segment_id"]
        panel_ids = scene.get("panels") or []
        if not panel_ids:
            continue
        panel_idx = panel_ids[0]
        if panel_idx >= len(state["panels"]):
            continue
        panel = state["panels"][panel_idx]
        page_path = panel["page_path"]
        if page_path not in page_cache:
            page_cache[page_path] = supabase_admin.storage.from_("pages").download(page_path)
        try:
            thumbnails[segment_id] = panel_thumbnail_jpeg(
                page_cache[page_path],
                panel["bbox"],
            )
        except Exception:
            logger.warning(
                "[pipeline] job_id=%s node=generate_narration thumbnail_failed segment_id=%s",
                state.get("job_id"),
                segment_id,
                exc_info=True,
            )

    return thumbnails


def generate_narration_node(state: PipelineState) -> PipelineState:
    """Generate Hindi narration for story scenes (DeepSeek text or Gemini + thumbnails)."""
    from core.config import settings
    from core.narration import generate_narration_batch

    story_scenes = [
        {
            "scene_index": scene["scene_index"],
            "segment_id": scene["segment_id"],
            "text": scene["text"],
            "panels": scene.get("panels") or [],
        }
        for scene in state["scenes"]
        if scene.get("is_story") and scene.get("text", "").strip()
    ]

    panel_thumbnails = (
        _build_panel_thumbnails(state, story_scenes)
        if settings.narration_backend == "gemini"
        else {}
    )
    narration_by_id = generate_narration_batch(
        series_context=state.get("series_context", ""),
        chapter_info=state.get("chapter_info", {}),
        story_scenes=story_scenes,
        panel_thumbnails=panel_thumbnails,
    )

    narrations = []
    for scene in state["scenes"]:
        segment_id = scene["segment_id"]
        if not scene.get("is_story") or not scene.get("text", "").strip():
            narrations.append({
                "scene_index": scene["scene_index"],
                "segment_id": segment_id,
                "narration_text": "",
            })
            continue

        narration_text = narration_by_id.get(segment_id, "").strip()
        narration_text = re.sub(r"\([^)]*\)", "", narration_text).strip()
        narrations.append({
            "scene_index": scene["scene_index"],
            "segment_id": segment_id,
            "narration_text": narration_text,
        })

    state["narration"] = narrations
    state["story_summary"] = assemble_story_summary(narrations)
    state["status"] = "SCRIPT_GENERATING"
    update_job_status(state["job_id"], state["status"])
    return state


def synthesize_audio_node(state: PipelineState) -> PipelineState:
    """Generate per-scene TTS in parallel and one correctly encoded master track."""
    import edge_tts
    from pydub import AudioSegment
    from core.config import settings

    async def generate_audio(text: str, voice: str = "hi-IN-SwaraNeural") -> bytes:
        communicate = edge_tts.Communicate(text, voice)
        audio_bytes = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_bytes.write(chunk["data"])
        return audio_bytes.getvalue()

    async def synthesize_all() -> tuple[list[dict], list[dict], AudioSegment]:
        semaphore = asyncio.Semaphore(settings.tts_concurrency)
        audio_urls: list[dict] = []
        timings: list[dict] = []
        master_audio = AudioSegment.empty()

        items = [item for item in state["narration"] if item.get("narration_text", "").strip()]

        async def fetch_tts(item: dict) -> tuple[dict, bytes]:
            async with semaphore:
                data = await generate_audio(item["narration_text"])
            return item, data

        tts_results = await asyncio.gather(*[fetch_tts(item) for item in items])

        for narration_item, audio_data in tts_results:
            scene_idx = narration_item["scene_index"]
            segment_id = narration_item.get("segment_id", f"scene_{scene_idx:04d}")
            decoded_segment = AudioSegment.from_file(io.BytesIO(audio_data), format="mp3")
            start_time = len(master_audio) / 1000.0
            master_audio += decoded_segment
            end_time = len(master_audio) / 1000.0

            storage_path = f"{state['job_id']}/audio/{segment_id}.mp3"
            try:
                supabase_admin.storage.from_("audio").upload(
                    path=storage_path,
                    file=audio_data,
                    file_options={"content-type": "audio/mpeg"},
                )
            except Exception as e:
                if "Duplicate" not in str(e) and "409" not in str(e):
                    raise

            audio_urls.append({"segment_id": segment_id, "path": storage_path})
            timings.append({
                "segment_id": segment_id,
                "scene_index": scene_idx,
                "start_time": start_time,
                "end_time": end_time,
                "duration": end_time - start_time,
            })

        return audio_urls, timings, master_audio

    audio_urls, timings, master_audio = asyncio.run(synthesize_all())

    if len(master_audio) > 0:
        combined_buffer = io.BytesIO()
        master_audio.export(combined_buffer, format="mp3", bitrate="128k")
        combined_audio_data = combined_buffer.getvalue()
        combined_path = f"{state['job_id']}/audio/combined.mp3"
        try:
            supabase_admin.storage.from_("audio").upload(
                path=combined_path,
                file=combined_audio_data,
                file_options={"content-type": "audio/mpeg"}
            )
        except Exception as e:
            if "Duplicate" not in str(e) and "409" not in str(e):
                print(f"Failed to upload combined audio: {e}")
        state["combined_audio_path"] = combined_path
        state["combined_audio_url"] = ""
    else:
        state["combined_audio_path"] = ""
        state["combined_audio_url"] = ""

    state["audio_urls"] = audio_urls
    state["timings"] = timings
    state["status"] = "TTS_COMPLETED"
    update_job_status(state["job_id"], state["status"])
    return state


def build_pipeline_graph():
    graph = StateGraph(PipelineState)

    nodes = {
        "extract_pages": extract_pages_node,
        "detect_panels": detect_panels_node,
        "crop_and_ocr": crop_and_ocr_node,
        "apply_chapter_metadata": apply_chapter_metadata_node,
        "build_scenes": build_scenes_node,
        "generate_narration": generate_narration_node,
        "synthesize_audio": synthesize_audio_node,
    }
    for name, fn in nodes.items():
        graph.add_node(name, _wrap_pipeline_node(name, fn))

    graph.set_entry_point("extract_pages")
    graph.add_edge("extract_pages", "detect_panels")
    graph.add_edge("detect_panels", "crop_and_ocr")
    graph.add_edge("crop_and_ocr", "apply_chapter_metadata")
    graph.add_edge("apply_chapter_metadata", "build_scenes")
    graph.add_edge("build_scenes", "generate_narration")
    graph.add_edge("generate_narration", "synthesize_audio")
    graph.add_edge("synthesize_audio", END)

    return graph.compile()


def run_pipeline(state: PipelineState):
    graph = build_pipeline_graph()
    final_state = graph.invoke(state)
    return final_state
