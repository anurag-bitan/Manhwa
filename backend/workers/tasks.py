import io
import logging
import tempfile
import time
from pathlib import Path

from PIL import Image
from storage3.exceptions import StorageApiError
import numpy as np
import pypdfium2 as pdfium
from paddleocr import PaddleOCR

from core.job_log import agent_debug_log
from core.page_ops import assign_lines_to_panels, panels_for_page
from db.supabase_admin import supabase_admin

logger = logging.getLogger(__name__)

PAGE_RENDER_SCALE = 1.0
JPEG_QUALITY = 70
OCR_MAX_WIDTH = 900

_page_bytes: dict[str, bytes] = {}
_ocr = None
_detect_stats = {"pages": 0, "boxes": 0, "download_sec": 0.0, "cpu_sec": 0.0, "download_bytes": 0}
_ocr_stats = {
    "panels": 0,
    "unique_pages": 0,
    "download_sec": 0.0,
    "ocr_sec": 0.0,
    "download_bytes": 0,
    "seen_pages": set(),
}


def reset_detect_stats() -> None:
    _detect_stats.update(pages=0, boxes=0, download_sec=0.0, cpu_sec=0.0, download_bytes=0)


def reset_ocr_stats() -> None:
    _ocr_stats.update(
        panels=0,
        unique_pages=0,
        download_sec=0.0,
        ocr_sec=0.0,
        download_bytes=0,
        seen_pages=set(),
    )


def flush_detect_stats(job_id: str) -> None:
    # #region agent log
    agent_debug_log(
        "H2",
        "workers/tasks.py:detect_panels",
        "panel detection storage vs cpu",
        {
            "job_id": job_id,
            "pages": _detect_stats["pages"],
            "boxes": _detect_stats["boxes"],
            "download_sec": round(_detect_stats["download_sec"], 2),
            "cpu_sec": round(_detect_stats["cpu_sec"], 2),
            "download_bytes": _detect_stats["download_bytes"],
        },
    )
    # #endregion


def flush_ocr_stats(job_id: str) -> None:
    # #region agent log
    agent_debug_log(
        "H2",
        "workers/tasks.py:crop_and_ocr",
        "ocr storage vs paddle",
        {
            "job_id": job_id,
            "panels": _ocr_stats["panels"],
            "unique_pages": _ocr_stats["unique_pages"],
            "repeated_downloads": max(0, _ocr_stats["panels"] - _ocr_stats["unique_pages"]),
            "download_sec": round(_ocr_stats["download_sec"], 2),
            "ocr_sec": round(_ocr_stats["ocr_sec"], 2),
            "download_bytes": _ocr_stats["download_bytes"],
        },
    )
    # #endregion


def _tmp_page_path(storage_path: str) -> Path:
    safe = storage_path.replace("/", "_").replace("\\", "_")
    return Path(tempfile.gettempdir()) / "manhwa-pages" / safe


def cache_page_bytes(storage_path: str, data: bytes) -> None:
    _page_bytes[storage_path] = data
    tmp = _tmp_page_path(storage_path)
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(data)


def get_page_bytes(storage_path: str) -> bytes:
    cached = _page_bytes.get(storage_path)
    if cached:
        return cached
    tmp = _tmp_page_path(storage_path)
    if tmp.is_file():
        data = tmp.read_bytes()
        _page_bytes[storage_path] = data
        return data
    data = supabase_admin.storage.from_("pages").download(storage_path)
    cache_page_bytes(storage_path, data)
    return data


def clear_page_cache(job_id: str | None = None) -> None:
    prefix = f"{job_id}/" if job_id else ""
    for path in list(_page_bytes):
        if not prefix or path.startswith(prefix):
            _page_bytes.pop(path, None)
            tmp = _tmp_page_path(path)
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


def get_ocr():
    global _ocr
    if _ocr is None:
        logger.info("[pipeline] PaddleOCR loading models (first run downloads ~100 MB)")
        _ocr = PaddleOCR(lang="en")
        logger.info("[pipeline] PaddleOCR ready")
    return _ocr


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


def _find_spine_gap(img, min_gap_width=15):
    """Find vertical white gap near centre for double-page spreads."""
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


def _gutter_boxes(img) -> list[list[int]]:
    h, w = img.shape
    all_boxes = []
    if w > h * 1.2:
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
                    all_boxes.append([x_off + bx1, y_off + by1, x_off + bx2, y_off + by2])
    else:
        col_boxes = _split_into_columns(img)
        for col_x1, col_x2 in col_boxes:
            col_img = img[:, col_x1:col_x2]
            panel_rows = _split_into_rows(col_img, col_x1)
            all_boxes.extend(panel_rows)
    all_boxes.sort(key=lambda b: b[1])
    return all_boxes


def _pil_to_jpeg_bytes(pil_image: Image.Image, quality: int = JPEG_QUALITY) -> bytes:
    rgb = pil_image.convert("RGB")
    buffer = io.BytesIO()
    rgb.save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


def _page_storage_path(job_id: str, page_num: int) -> str:
    return f"{job_id}/pages/page_{page_num:04d}.jpg"


def _upload_page_jpeg(storage_path: str, img_bytes: bytes) -> None:
    try:
        supabase_admin.storage.from_("pages").upload(
            path=storage_path,
            file=img_bytes,
            file_options={"content-type": "image/jpeg"},
        )
    except StorageApiError as exc:
        if "Duplicate" not in str(exc) and "409" not in str(exc):
            raise


def load_client_pages(job_id: str, page_count: int) -> list[dict]:
    pages = []
    for page_num in range(page_count):
        storage_path = _page_storage_path(job_id, page_num)
        img_bytes = supabase_admin.storage.from_("pages").download(storage_path)
        if not img_bytes:
            raise ValueError(f"Client page missing: {storage_path}")
        cache_page_bytes(storage_path, img_bytes)
        pages.append({"path": storage_path})
    logger.info(
        "[pipeline] job_id=%s task=extract_pages using client_pages count=%s",
        job_id,
        len(pages),
    )
    return pages


def extract_pages(pdf_storage_path: str, job_id: str, client_page_count: int = 0):
    if client_page_count:
        try:
            return load_client_pages(job_id, client_page_count)
        except Exception:
            logger.exception(
                "[pipeline] job_id=%s client pages unavailable, rendering on server",
                job_id,
            )

    logger.info(
        "[pipeline] job_id=%s task=extract_pages download path=%s",
        job_id,
        pdf_storage_path,
    )
    pdf_bytes = supabase_admin.storage.from_("pdfs").download(pdf_storage_path)
    pdf = pdfium.PdfDocument(pdf_bytes)
    page_count = len(pdf)
    logger.info(
        "[pipeline] job_id=%s task=extract_pages rendering page_count=%s scale=%s jpeg=%s",
        job_id,
        page_count,
        PAGE_RENDER_SCALE,
        JPEG_QUALITY,
    )

    page_data_list = []
    render_sec = 0.0
    upload_sec = 0.0
    total_bytes = 0
    for page_num in range(page_count):
        page = pdf[page_num]
        render_started = time.perf_counter()
        bitmap = page.render(scale=PAGE_RENDER_SCALE)
        pil_image = bitmap.to_pil()
        img_bytes = _pil_to_jpeg_bytes(pil_image)
        render_sec += time.perf_counter() - render_started
        total_bytes += len(img_bytes)

        storage_path = _page_storage_path(job_id, page_num)
        cache_page_bytes(storage_path, img_bytes)
        upload_started = time.perf_counter()
        _upload_page_jpeg(storage_path, img_bytes)
        upload_sec += time.perf_counter() - upload_started
        page_data_list.append({"path": storage_path})

    pdf.close()
    # #region agent log
    agent_debug_log(
        "H3",
        "workers/tasks.py:extract_pages",
        "page render vs storage upload",
        {
            "job_id": job_id,
            "pages": page_count,
            "png_bytes": total_bytes,
            "render_sec": round(render_sec, 2),
            "upload_sec": round(upload_sec, 2),
            "scale": PAGE_RENDER_SCALE,
            "format": "JPEG",
        },
    )
    # #endregion
    logger.info(
        "[pipeline] job_id=%s task=extract_pages done uploaded_pages=%s jpeg_bytes=%s",
        job_id,
        len(page_data_list),
        total_bytes,
    )
    return page_data_list


def detect_panels(page_path: str, page_number: int):
    """Detect panels on any page layout (single, spread, tall strip)."""
    download_started = time.perf_counter()
    img_bytes = get_page_bytes(page_path)
    download_sec = time.perf_counter() - download_started
    cpu_started = time.perf_counter()
    pil_img = Image.open(io.BytesIO(img_bytes)).convert("L")
    img = np.array(pil_img)
    h, w = img.shape
    gutter_boxes = _gutter_boxes(img)
    all_boxes = panels_for_page(w, h, gutter_boxes)

    _detect_stats["pages"] += 1
    _detect_stats["boxes"] += len(all_boxes)
    _detect_stats["download_sec"] += download_sec
    _detect_stats["cpu_sec"] += time.perf_counter() - cpu_started
    _detect_stats["download_bytes"] += len(img_bytes)
    return {"page_number": page_number, "boxes": all_boxes}


def _iter_ocr_lines(result) -> list[tuple[object, str]]:
    lines: list[tuple[object, str]] = []
    if not result:
        return lines
    page = result[0]
    if page is None:
        return lines
    if isinstance(page, dict):
        texts = page.get("rec_texts") or []
        boxes = page.get("rec_boxes") or page.get("dt_polys") or []
        for box, text in zip(boxes, texts):
            lines.append((box, str(text)))
        return lines
    for item in page:
        if not item or len(item) < 2:
            continue
        box, payload = item[0], item[1]
        text = payload[0] if isinstance(payload, (list, tuple)) else str(payload)
        lines.append((box, str(text)))
    return lines


def ocr_page_panels(page_path: str, panels: list[dict]) -> list[dict]:
    """Run PaddleOCR once per page and assign lines to panel boxes."""
    download_started = time.perf_counter()
    img_bytes = get_page_bytes(page_path)
    download_sec = time.perf_counter() - download_started
    page_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    ocr_img = page_img
    if ocr_img.width > OCR_MAX_WIDTH:
        ratio = OCR_MAX_WIDTH / ocr_img.width
        ocr_img = ocr_img.resize((OCR_MAX_WIDTH, max(1, int(ocr_img.height * ratio))), Image.LANCZOS)
        scale = page_img.width / ocr_img.width
    else:
        scale = 1.0

    ocr_started = time.perf_counter()
    result = get_ocr().ocr(np.array(ocr_img))
    ocr_sec = time.perf_counter() - ocr_started
    raw_lines = _iter_ocr_lines(result)
    if scale != 1.0:
        scaled_lines = []
        for box, text in raw_lines:
            if hasattr(box, "tolist"):
                box = box.tolist()
            try:
                scaled_box = [[float(pt[0]) * scale, float(pt[1]) * scale] for pt in box]
            except (TypeError, IndexError):
                scaled_box = box
            scaled_lines.append((scaled_box, text))
        raw_lines = scaled_lines

    assigned = assign_lines_to_panels(raw_lines, panels)
    _ocr_stats["panels"] += len(panels)
    if page_path not in _ocr_stats["seen_pages"]:
        _ocr_stats["seen_pages"].add(page_path)
        _ocr_stats["unique_pages"] += 1
    _ocr_stats["download_sec"] += download_sec
    _ocr_stats["ocr_sec"] += ocr_sec
    _ocr_stats["download_bytes"] += len(img_bytes)
    return assigned


def crop_and_ocr(panel_data: dict, panel_index: int):
    """Backward-compatible single-panel OCR using the page cache and one page OCR when possible."""
    panel = {**panel_data, "panel_index": panel_index}
    results = ocr_page_panels(panel_data["page_path"], [panel])
    return results[0] if results else {
        "panel_index": panel_index,
        "text": "",
        "bbox": panel_data.get("bbox"),
        "page_number": panel_data.get("page_number", 0),
    }
