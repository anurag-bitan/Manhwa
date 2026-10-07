"""Page JPEG encoding and OCR-line to panel mapping (no Paddle/Supabase imports)."""

from __future__ import annotations

import io
from typing import Any, Iterable

from PIL import Image


JPEG_QUALITY = 80
RENDER_SCALE = 1


def encode_jpeg(pil_image: Image.Image, quality: int = JPEG_QUALITY) -> bytes:
    buf = io.BytesIO()
    pil_image.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def quad_to_xyxy(box: Iterable[Iterable[float]]) -> list[float]:
    points = list(box)
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def line_center(bbox: list[float]) -> tuple[float, float]:
    x1, y1, x2, y2 = (float(v) for v in bbox)
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def point_in_bbox(point: tuple[float, float], bbox: list[float]) -> bool:
    x, y = point
    x1, y1, x2, y2 = (float(v) for v in bbox)
    left, right = (x1, x2) if x1 <= x2 else (x2, x1)
    top, bottom = (y1, y2) if y1 <= y2 else (y2, y1)
    return left <= x <= right and top <= y <= bottom


def iou(a: list[float], b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = (float(v) for v in a)
    bx1, by1, bx2, by2 = (float(v) for v in b)
    if ax1 > ax2:
        ax1, ax2 = ax2, ax1
    if ay1 > ay2:
        ay1, ay2 = ay2, ay1
    if bx1 > bx2:
        bx1, bx2 = bx2, bx1
    if by1 > by2:
        by1, by2 = by2, by1
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union else 0.0


def parse_paddle_lines(result: Any) -> list[dict[str, Any]]:
    """Normalize PaddleOCR output to [{bbox, text}, ...]."""
    if not result:
        return []
    page = result[0] if isinstance(result, list) else result
    if not page:
        return []
    lines: list[dict[str, Any]] = []
    for item in page:
        if not item or len(item) < 2:
            continue
        box, rec = item[0], item[1]
        text = rec[0] if isinstance(rec, (list, tuple)) else str(rec)
        text = (text or "").strip()
        if not text:
            continue
        try:
            bbox = quad_to_xyxy(box)
        except (TypeError, IndexError, ValueError):
            continue
        lines.append({"bbox": bbox, "text": text})
    return lines


def assign_ocr_text_to_panels(
    lines: list[dict[str, Any]],
    panels: list[dict[str, Any]],
    *,
    min_iou: float = 0.05,
) -> list[str]:
    """Map page OCR lines onto panel boxes (center-in-box, then IoU)."""
    buckets: list[list[str]] = [[] for _ in panels]
    for line in lines:
        bbox = line.get("bbox") or []
        text = (line.get("text") or "").strip()
        if len(bbox) != 4 or not text:
            continue
        matched: int | None = None
        center = line_center(bbox)
        for i, panel in enumerate(panels):
            panel_bbox = panel.get("bbox") or []
            if len(panel_bbox) == 4 and point_in_bbox(center, panel_bbox):
                matched = i
                break
        if matched is None:
            best_i, best_iou = -1, 0.0
            for i, panel in enumerate(panels):
                panel_bbox = panel.get("bbox") or []
                if len(panel_bbox) != 4:
                    continue
                score = iou(bbox, panel_bbox)
                if score > best_iou:
                    best_i, best_iou = i, score
            if best_iou >= min_iou:
                matched = best_i
        if matched is not None:
            buckets[matched].append(text)
    return [" ".join(parts).strip() for parts in buckets]
