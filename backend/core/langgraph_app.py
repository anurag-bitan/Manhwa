from langgraph.graph import StateGraph, END
from typing import TypedDict, List, Optional
from db.supabase_admin import supabase_admin
import asyncio
import re
import json

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
    rolling_summary: str        # kept for compatibility, not actively used
    narration: List[dict]
    error: Optional[str]
    audio_urls: List[dict]
    combined_audio_path: str
    combined_audio_url: str
    timings: List[dict]
    manhwa_name: str
    genre: str
    chapter_number: str

def extract_pages_node(state: PipelineState) -> PipelineState:
    """Extract pages inside the current pipeline job."""
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
    """Quickly push the current status to the DB."""
    try:
        supabase_admin.table("processing_jobs").update({"status": status}).eq("id", job_id).execute()
    except Exception as e:
        print(f"Failed to update job status: {e}")


def crop_and_ocr_node(state: PipelineState) -> PipelineState:
    """Crop each panel and run OCR inside the current pipeline job."""
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

def detect_chapter_and_storyline_node(state: PipelineState) -> PipelineState:
    """Identify the manhwa, chapter, and provide series context using Groq."""
    from groq import Groq
    from core.config import settings
    print("In detect_chapter_and_storyline_node")
    client = Groq(api_key=settings.groq_api_key)

    # If user provided info, use it directly
    if state.get("manhwa_name") and state.get("chapter_number"):
        state["chapter_info"] = {
            "title": state["manhwa_name"],
            "chapter": f"Chapter {state['chapter_number']}",
            "is_correct": True
        }
        # Generate context via LLM still
        ocr_text = " ".join([ocr["text"] for ocr in state["ocr_results"][:3] if ocr["text"]])[:1500]
        prompt = f"""You are a manhwa expert. The manhwa is "{state['manhwa_name']}" (genre: {state.get('genre', 'unknown')}), chapter {state['chapter_number']}.
        Write a 3-5 sentence series context that describes the story up to this chapter. Include the protagonist's name, their goal, and recent events.
        OCR from first pages: {ocr_text}
        Respond ONLY with the context string, no extra text."""
        resp = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=300,
        )
        state["series_context"] = resp.choices[0].message.content.strip()
        state["status"] = "CHAPTER_DETECTED"
        update_job_status(state["job_id"], state["status"])
        return state

    # Otherwise infer
    ocr_text = " ".join([ocr["text"] for ocr in state["ocr_results"][:3] if ocr["text"]])[:2000]
    prompt = f"""You are an expert manhwa analyst. You have OCR text from the first pages of a manhwa PDF.

    Your tasks:
    1. **Identify the manhwa title** (e.g., "Solo Leveling").
    2. **Identify the chapter number** – if the OCR seems to start in the middle of a chapter, detect the actual chapter.
    3. **Auto‑correct** if the OCR suggests a chapter that doesn't match the story's typical numbering.
    4. **Write a short series context** (3-5 sentences) that describes the story up to **this** chapter, so a YouTube narrator can seamlessly introduce the episode.

    ##STRICT NOTE :
    Respond ONLY with a JSON object with these keys:
    - "title": string
    - "chapter": string (e.g., "Chapter 5")
    - "is_correct": boolean (whether you corrected the chapter)
    - "context": string (the story background)

    OCR text:
    {ocr_text}
    """
    try:
        resp = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=400,
        )
        raw = resp.choices[0].message.content.strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            state["chapter_info"] = data
            state["series_context"] = data["context"]
        else:
            raise ValueError("No JSON found")
    except Exception as e:
        state["chapter_info"] = {"title": "Unknown", "chapter": "Chapter ?", "is_correct": False}
        state["series_context"] = "A manhwa story."

    state["status"] = "CHAPTER_DETECTED"
    return state



def build_scenes_node(state: PipelineState) -> PipelineState:
    print("buildinf scences .......")
    """Group panels into scenes, skipping author‑notes / intro pages."""
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

def generate_narration_node(state: PipelineState) -> PipelineState:
    """Generate Hindi narration for each scene, with full story context."""
    from groq import Groq
    from core.config import settings

    client = Groq(api_key=settings.groq_api_key)

    series_context = state.get("series_context", "")
    chapter = state.get("chapter_info", {}).get("chapter", "")

    narrations = []
    prev_text = ""   # only the last panel's narration

    for scene in state["scenes"]:
        if not scene["is_story"] or not scene["text"].strip():
            narrations.append({
                "scene_index": scene["scene_index"],
                "segment_id": scene["segment_id"],
                "narration_text": "",
            })
            continue

        ocr_text = scene["text"]

        # For the first panel, optionally inject series context (intro)
        if len(narrations) == 0 and series_context:
            intro = f"Series background (use ONLY for the first sentence): {series_context}"
        else:
            intro = ""

        prompt = f"""You are a Hindi YouTube storyteller narrating a manhwa panel.  
Your style is energetic, conversational, and lightly humorous – like a friend explaining a cool comic.

STRICT RULES:
- Write exactly 2‑3 sentences of spoken Hindi based SOLELY on the given OCR text.
- Describe what is happening in THIS panel – actions, dialogue, or visual cues from the OCR.
- Add a tiny pinch of humour or an exaggerated reaction only if it fits naturally.
- Never repeat anything from the previous panel's narration.
- No stage directions, no brackets, pure spoken words.

{intro}

Previous panel's narration (just to avoid repetition): {prev_text[:80]}

OCR text from THIS panel:
{ocr_text}

Hindi narration (only for this panel):"""


        try:
            response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=200,
        )
        except Exception as e:
            print(f"Narration generation failed: {e}")
            raise
        
        narration_text = response.choices[0].message.content.strip()
        narration_text = re.sub(r'\([^)]*\)', '', narration_text).strip()

        narrations.append({
            "scene_index": scene["scene_index"],
            "segment_id": scene["segment_id"],
            "narration_text": narration_text
        })
        prev_text = narration_text   # update for next iteration

    state["narration"] = narrations
    state["status"] = "SCRIPT_GENERATING"
    update_job_status(state["job_id"], state["status"])
    return state



def synthesize_audio_node(state: PipelineState) -> PipelineState:
    """Generate per-scene TTS and one correctly encoded master track."""
    import edge_tts
    import io
    from pydub import AudioSegment

    async def generate_audio(text: str, voice: str = "hi-IN-SwaraNeural") -> bytes:
        communicate = edge_tts.Communicate(text, voice)
        audio_bytes = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_bytes.write(chunk["data"])
        return audio_bytes.getvalue()

    audio_urls = []
    timings = []
    master_audio = AudioSegment.empty()

    for narration_item in state["narration"]:
        scene_idx = narration_item["scene_index"]
        segment_id = narration_item.get("segment_id", f"scene_{scene_idx:04d}")
        text = narration_item["narration_text"]

        if not text.strip():
            continue

        audio_data = asyncio.run(generate_audio(text))
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

    # Concatenate decoded audio and encode once. Joining MP3 bytes directly can
    # add headers and encoder padding between scenes, causing timestamp drift.
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
            if "Duplicate" in str(e) or "409" in str(e):
                pass
            else:
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




# --- Graph construction ---
def build_pipeline_graph():
    graph = StateGraph(PipelineState)

    graph.add_node("extract_pages", extract_pages_node)
    graph.add_node("detect_panels", detect_panels_node)
    graph.add_node("crop_and_ocr", crop_and_ocr_node)
    graph.add_node("detect_chapter", detect_chapter_and_storyline_node)
    graph.add_node("build_scenes", build_scenes_node)
    graph.add_node("generate_narration", generate_narration_node)
    graph.add_node("synthesize_audio", synthesize_audio_node)

    graph.set_entry_point("extract_pages")
    graph.add_edge("extract_pages", "detect_panels")
    graph.add_edge("detect_panels", "crop_and_ocr")
    graph.add_edge("crop_and_ocr", "detect_chapter")
    graph.add_edge("detect_chapter", "build_scenes")
    graph.add_edge("build_scenes", "generate_narration")
    graph.add_edge("generate_narration", "synthesize_audio")
    graph.add_edge("synthesize_audio", END)

    return graph.compile()

def run_pipeline(state: PipelineState):
    graph = build_pipeline_graph()
    final_state = graph.invoke(state)
    return final_state

# The describe_panels_node function is kept below but not used in the graph.
# You may delete it entirely if you don't plan to use it again.

def describe_panels_node(state: PipelineState) -> PipelineState:
    """Use Groq Vision to describe each panel using base64 image data."""
    from groq import Groq
    from core.config import settings
    import base64
    from db.supabase_admin import supabase_admin

    client = Groq(api_key=settings.groq_api_key)
    descriptions = []

    for panel in state["panels"]:
        page_path = panel["page_path"]
        img_bytes = supabase_admin.storage.from_("pages").download(page_path)
        img_base64 = base64.b64encode(img_bytes).decode("utf-8")
        image_data_url = f"data:image/png;base64,{img_base64}"

        # This model may not be available – update if you find a working one.
        response = client.chat.completions.create(
            model="llava-v1.5-7b",   # NOT WORKING currently, kept for reference
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this manhwa panel: who is in it, what are they doing, their expressions, and any important actions. 2-3 concise sentences."},
                    {"type": "image_url", "image_url": {"url": image_data_url}}
                ]
            }],
            max_tokens=200,
            temperature=0.3
        )
        descriptions.append(response.choices[0].message.content.strip())

    state["panel_descriptions"] = descriptions
    state["status"] = "PANELS_DESCRIBED"
    update_job_status(state["job_id"], state["status"])
    return state
