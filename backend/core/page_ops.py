"""Pure geometry helpers for panel slicing and OCR line assignment."""

from __future__ import annotations

MAX_PANELS_PER_PAGE = 4
TALL_ASPECT_RATIO = 1.6
MAX_TALL_SLICES = 3


def even_vertical_slices(width: int, height: int, count: int) -> list[list[int]]:
    count = max(1, min(int(count), MAX_PANELS_PER_PAGE))
    slice_h = max(1, height // count)
    boxes: list[list[int]] = []
    for index in range(count):
        y1 = index * slice_h
        y2 = height if index == count - 1 else (index + 1) * slice_h
        boxes.append([0, y1, width, y2])
    return boxes


def panels_for_page(width: int, height: int, gutter_boxes: list[list[int]] | None = None) -> list[list[int]]:
    """Prefer 1-3 vertical slices for tall manhwa; otherwise cap gutter boxes."""
    if height <= 0 or width <= 0:
        return [[0, 0, max(width, 1), max(height, 1)]]

    aspect = height / max(width, 1)
    if aspect >= TALL_ASPECT_RATIO:
        slices = min(MAX_TALL_SLICES, max(1, round(aspect / 1.4)))
        return even_vertical_slices(width, height, slices)

    boxes = [list(box) for box in (gutter_boxes or []) if len(box) == 4]
    if not boxes:
        return [[0, 0, width, height]]
    if len(boxes) > MAX_PANELS_PER_PAGE:
        return even_vertical_slices(width, height, MAX_PANELS_PER_PAGE)
    return boxes


def box_center(points) -> tuple[float, float] | None:
    if points is None:
        return None
    xs: list[float] = []
    ys: list[float] = []
    if hasattr(points, "tolist"):
        points = points.tolist()
    if isinstance(points, (list, tuple)) and points and isinstance(points[0], (int, float)):
        if len(points) >= 4:
            xs = [float(points[0]), float(points[2])]
            ys = [float(points[1]), float(points[3])]
    else:
        try:
            for point in points:
                xs.append(float(point[0]))
                ys.append(float(point[1]))
        except (TypeError, IndexError, ValueError):
            return None
    if not xs or not ys:
        return None
    return sum(xs) / len(xs), sum(ys) / len(ys)


def point_in_bbox(x: float, y: float, bbox: list[int]) -> bool:
    x1, y1, x2, y2 = bbox
    return x1 <= x <= x2 and y1 <= y <= y2


def assign_lines_to_panels(
    lines: list[tuple[object, str]],
    panels: list[dict],
) -> list[dict]:
    """Map OCR lines (box, text) onto panel dicts that already have bbox/page fields."""
    buckets: list[list[str]] = [[] for _ in panels]
    for box, text in lines:
        cleaned = (text or "").strip()
        if not cleaned:
            continue
        center = box_center(box)
        if center is None:
            continue
        cx, cy = center
        matched = False
        for index, panel in enumerate(panels):
            bbox = panel.get("bbox") or []
            if len(bbox) == 4 and point_in_bbox(cx, cy, bbox):
                buckets[index].append(cleaned)
                matched = True
                break
        if not matched and buckets:
            buckets[0].append(cleaned)

    results = []
    for index, panel in enumerate(panels):
        results.append({
            "panel_index": panel.get("panel_index", index),
            "text": " ".join(buckets[index]).strip() if index < len(buckets) else "",
            "bbox": panel.get("bbox"),
            "page_number": panel.get("page_number", 0),
        })
    return results
