import logging
from collections import defaultdict

from db.supabase_admin import supabase_admin
from storage3.exceptions import StorageApiError
import pypdfium2 as pdfium
from PIL import Image
import io
import numpy as np
from paddleocr import PaddleOCR

from core.config import settings
from core.page_ops import (
    RENDER_SCALE,
    assign_ocr_text_to_panels,
    encode_jpeg,
    parse_paddle_lines,
)

logger = logging.getLogger(__name__)

# job_id -> {storage_path: jpeg bytes}
_page_bytes: dict[str, dict[str, bytes]] = defaultdict(dict)

# -------------------------------------------------------------------
# Global PaddleOCR reader (loaded once when worker starts)
# -------------------------------------------------------------------
_ocr = None

def get_ocr():
    global _ocr
    if _ocr is None:
        logger.info("[pipeline] PaddleOCR loading models (first run downloads ~100 MB)")
        try:
            _ocr = PaddleOCR(lang="en", use_angle_cls=False, show_log=False)
        except TypeError:
            _ocr = PaddleOCR(lang="en", use_angle_cls=False)
        logger.info("[pipeline] PaddleOCR ready engine=%s", settings.ocr_engine)
    return _ocr


def cache_page_bytes(job_id: str, page_path: str, img_bytes: bytes) -> None:
    _page_bytes[job_id][page_path] = img_bytes


def load_page_bytes(page_path: str, job_id: str | None = None) -> bytes:
    if job_id:
        cached = _page_bytes.get(job_id, {}).get(page_path)
        if cached:
            return cached
    img_bytes = supabase_admin.storage.from_("pages").download(page_path)
    if job_id:
        cache_page_bytes(job_id, page_path, img_bytes)
    return img_bytes


def clear_page_cache(job_id: str) -> None:
    _page_bytes.pop(job_id, None)


# -------------------------------------------------------------------
# Heuristic panel detection helpers (projection‑based)
# -------------------------------------------------------------------
def _split_into_columns(img, min_vertical_gap_width=30):
    """Detect vertical white gutters and return column boundaries."""
    vertical_profile = np.mean(img, axis=0)
    white_mask = vertical_profile > 240

    col_gaps = []
    in_gap = False
    start = 0
    for i, white in enumerate(white_mask):
        if white and not in_gap:
            start = i
            in_gap = True
        elif not white and in_gap:
            gap_width = i - start
            if gap_width >= min_vertical_gap_width:
                col_gaps.append((start, i))
            in_gap = False
    if in_gap:
        gap_width = len(white_mask) - start
        if gap_width >= min_vertical_gap_width:
            col_gaps.append((start, len(white_mask)))

    if not col_gaps:
        return [(0, img.shape[1])]

    columns = []
    prev_x = 0
    for g_start, g_end in col_gaps:
        if g_start - prev_x > 50:
            columns.append((prev_x, g_start))
        prev_x = g_end
    if img.shape[1] - prev_x > 50:
        columns.append((prev_x, img.shape[1]))
    return columns if columns else [(0, img.shape[1])]


def _split_into_rows(col_img, col_offset_x, min_horizontal_gap_height=15):
    """Split a column image into panels using horizontal white gutters."""
    horizontal_profile = np.mean(col_img, axis=1)
    white_mask = horizontal_profile > 240

    row_gaps = []
    in_gap = False
    start = 0
    for i, white in enumerate(white_mask):
        if white and not in_gap:
            start = i
            in_gap = True
        elif not white and in_gap:
            gap_h = i - start
            if gap_h >= min_horizontal_gap_height:
                row_gaps.append((start, i))
            in_gap = False
    if in_gap:
        gap_h = len(white_mask) - start
        if gap_h >= min_horizontal_gap_height:
            row_gaps.append((start, len(white_mask)))

    if not row_gaps:
        h, w = col_img.shape
        return [[col_offset_x, 0, col_offset_x + w, h]]

    panels = []
    prev_y = 0
    for gap_start, gap_end in row_gaps:
        if gap_start - prev_y > 30:
            panels.append([col_offset_x, prev_y, col_offset_x + col_img.shape[1], gap_start])
        prev_y = gap_end
    if col_img.shape[0] - prev_y > 30:
        panels.append([col_offset_x, prev_y, col_offset_x + col_img.shape[1], col_img.shape[0]])
    return panels


def _find_spine_gap(img, search_ratio=0.2, min_gap_width=15):
    """Find vertical white gap near centre for double‑page spreads."""
    h, w = img.shape
    left_bound = int(w * 0.4)
    right_bound = int(w * 0.6)

    vertical_profile = np.mean(img[:, left_bound:right_bound], axis=0)
    white_mask = vertical_profile > 240
    best_start, best_end = None, None
    best_width = 0
    in_gap = False
    start = 0
    for i, white in enumerate(white_mask):
        if white and not in_gap:
            start = i
            in_gap = True
        elif not white and in_gap:
            gap_w = i - start
            if gap_w >= min_gap_width and gap_w > best_width:
                best_start, best_end = start, i
                best_width = gap_w
            in_gap = False
    if in_gap:
        gap_w = len(white_mask) - start
        if gap_w >= min_gap_width and gap_w > best_width:
            best_start, best_end = start, len(white_mask)

    if best_start is None:
        return None
    return left_bound + (best_start + best_end) // 2


# -------------------------------------------------------------------
# Synchronous processing functions used by one Cloud Run Job execution
# -------------------------------------------------------------------
def extract_pages(pdf_storage_path: str, job_id: str):
    clear_page_cache(job_id)
    logger.info(
        "[pipeline] job_id=%s task=extract_pages download path=%s",
        job_id,
        pdf_storage_path,
    )
    pdf_bytes = supabase_admin.storage.from_("pdfs").download(pdf_storage_path)
    pdf = pdfium.PdfDocument(pdf_bytes)
    page_count = len(pdf)
    logger.info(
        "[pipeline] job_id=%s task=extract_pages rendering page_count=%s",
        job_id,
        page_count,
    )

    page_data_list = []
    for page_num in range(page_count):
        page = pdf[page_num]
        bitmap = page.render(scale=RENDER_SCALE)
        pil_image = bitmap.to_pil()
        img_bytes = encode_jpeg(pil_image)

        storage_path = f"{job_id}/pages/page_{page_num:04d}.jpg"
        cache_page_bytes(job_id, storage_path, img_bytes)
        try:
            supabase_admin.storage.from_("pages").upload(
                path=storage_path,
                file=img_bytes,
                file_options={"content-type": "image/jpeg"}
            )
        except StorageApiError as e:
            if "Duplicate" in str(e) or "409" in str(e):
                logger.info(
                    "[pipeline] job_id=%s task=extract_pages page=%s already in storage",
                    job_id,
                    page_num,
                )
            else:
                raise
        # Persist object paths, not public URLs. The authenticated assets route
        # creates short-lived signed URLs after confirming job ownership.
        page_data_list.append({"path": storage_path})

    pdf.close()
    logger.info(
        "[pipeline] job_id=%s task=extract_pages done uploaded_pages=%s",
        job_id,
        len(page_data_list),
    )
    return page_data_list


def detect_panels(page_path: str, page_number: int, job_id: str | None = None):
    """Detect panels on any page layout (single, spread, partial spread)."""
    img_bytes = load_page_bytes(page_path, job_id)
    pil_img = Image.open(io.BytesIO(img_bytes)).convert('L')
    img = np.array(pil_img)

    h, w = img.shape
    all_boxes = []

    if w > h * 1.2:                     # wide page → possible spread
        spine_x = _find_spine_gap(img)
        if spine_x is not None:
            left_img = img[:, :spine_x]
            right_img = img[:, spine_x:]
            left_offset = (0, 0)
            right_offset = (spine_x, 0)
        else:
            mid = w // 2
            left_img = img[:, :mid]
            right_img = img[:, mid:]
            left_offset = (0, 0)
            right_offset = (mid, 0)

        for half_img, (x_off, y_off) in [(left_img, left_offset), (right_img, right_offset)]:
            if half_img.size == 0:
                continue
            col_boxes = _split_into_columns(half_img)
            for col_x1, col_x2 in col_boxes:
                col_img = half_img[:, col_x1:col_x2]
                panel_rows = _split_into_rows(col_img, col_x1)
                for bx1, by1, bx2, by2 in panel_rows:
                    all_boxes.append([x_off + bx1, y_off + by1,
                                      x_off + bx2, y_off + by2])
    else:
        col_boxes = _split_into_columns(img)
        for col_x1, col_x2 in col_boxes:
            col_img = img[:, col_x1:col_x2]
            panel_rows = _split_into_rows(col_img, col_x1)
            all_boxes.extend(panel_rows)

    all_boxes.sort(key=lambda b: b[1])
    return {"page_number": page_number, "boxes": all_boxes}


def _ocr_crop_text(page_img: Image.Image, bbox: list) -> str:
    x1, y1, x2, y2 = bbox
    cropped = page_img.crop((x1, y1, x2, y2))
    max_width = 800
    if cropped.width > max_width:
        ratio = max_width / cropped.width
        cropped = cropped.resize((max_width, int(cropped.height * ratio)), Image.LANCZOS)
    result = get_ocr().ocr(np.array(cropped))
    lines = parse_paddle_lines(result)
    return " ".join(line["text"] for line in lines).strip()


def crop_and_ocr(panel_data: dict, panel_index: int, job_id: str | None = None):
    """Crop a panel and run OCR, returning extracted text."""
    page_path = panel_data["page_path"]
    img_bytes = load_page_bytes(page_path, job_id)
    page_img = Image.open(io.BytesIO(img_bytes))

    text = _ocr_crop_text(page_img, panel_data["bbox"])
    return {
        "panel_index": panel_index,
        "text": text,
        "bbox": panel_data["bbox"],
        "page_number": panel_data["page_number"]
    }


def ocr_all_panels(panels: list[dict], job_id: str, on_first_page_done=None) -> list[dict]:
    """OCR each unique page once, then map lines onto panel boxes."""
    grouped: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for idx, panel in enumerate(panels):
        grouped[panel["page_path"]].append((idx, panel))

    results: list[dict | None] = [None] * len(panels)
    first_page = True
    for page_path, items in grouped.items():
        img_bytes = load_page_bytes(page_path, job_id)
        page_img = Image.open(io.BytesIO(img_bytes))
        page_np = np.array(page_img.convert("RGB"))
        lines = parse_paddle_lines(get_ocr().ocr(page_np))
        mapped = assign_ocr_text_to_panels(lines, [panel for _, panel in items])
        for (idx, panel), text in zip(items, mapped):
            if not text:
                text = _ocr_crop_text(page_img, panel["bbox"])
            results[idx] = {
                "panel_index": idx,
                "text": text,
                "bbox": panel["bbox"],
                "page_number": panel["page_number"],
            }
        if first_page and on_first_page_done:
            on_first_page_done()
            first_page = False

    return [row for row in results if row is not None]
