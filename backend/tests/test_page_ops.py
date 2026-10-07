import unittest

from core.page_ops import (
    assign_ocr_text_to_panels,
    encode_jpeg,
    iou,
    parse_paddle_lines,
    point_in_bbox,
    quad_to_xyxy,
)
from PIL import Image


class PageOpsTests(unittest.TestCase):
    def test_quad_to_xyxy(self):
        self.assertEqual(
            quad_to_xyxy([[10, 20], [40, 20], [40, 80], [10, 80]]),
            [10, 20, 40, 80],
        )

    def test_point_in_bbox(self):
        self.assertTrue(point_in_bbox((15, 25), [10, 20, 40, 80]))
        self.assertFalse(point_in_bbox((5, 25), [10, 20, 40, 80]))

    def test_iou_overlap(self):
        self.assertGreater(iou([0, 0, 10, 10], [5, 5, 15, 15]), 0)
        self.assertEqual(iou([0, 0, 10, 10], [20, 20, 30, 30]), 0)

    def test_assign_center_in_box(self):
        panels = [
            {"bbox": [0, 0, 100, 100]},
            {"bbox": [0, 100, 100, 200]},
        ]
        lines = [
            {"bbox": [10, 10, 40, 30], "text": "hello"},
            {"bbox": [10, 120, 40, 140], "text": "world"},
        ]
        self.assertEqual(assign_ocr_text_to_panels(lines, panels), ["hello", "world"])

    def test_assign_iou_fallback(self):
        panels = [{"bbox": [0, 0, 100, 100]}]
        lines = [{"bbox": [60, 10, 160, 90], "text": "edge"}]
        self.assertEqual(assign_ocr_text_to_panels(lines, panels), ["edge"])

    def test_parse_paddle_lines(self):
        raw = [[
            [[[0, 0], [10, 0], [10, 8], [0, 8]], ("Hi", 0.99)],
            [[[0, 20], [10, 20], [10, 28], [0, 28]], ("There", 0.9)],
        ]]
        lines = parse_paddle_lines(raw)
        self.assertEqual([line["text"] for line in lines], ["Hi", "There"])

    def test_encode_jpeg_is_jpeg(self):
        img = Image.new("RGB", (8, 8), color=(12, 24, 36))
        data = encode_jpeg(img, quality=80)
        self.assertTrue(data.startswith(b"\xff\xd8"))


if __name__ == "__main__":
    unittest.main()
