import unittest

from core.page_ops import assign_lines_to_panels, even_vertical_slices, panels_for_page


class PageOpsTests(unittest.TestCase):
    def test_tall_page_uses_few_vertical_slices(self):
        boxes = panels_for_page(800, 2400, gutter_boxes=[[0, 0, 800, 100]] * 12)
        self.assertGreaterEqual(len(boxes), 1)
        self.assertLessEqual(len(boxes), 3)
        self.assertEqual(boxes[0][0], 0)
        self.assertEqual(boxes[-1][3], 2400)

    def test_even_slices_cover_full_height(self):
        boxes = even_vertical_slices(600, 900, 3)
        self.assertEqual(len(boxes), 3)
        self.assertEqual(boxes[0], [0, 0, 600, 300])
        self.assertEqual(boxes[-1][3], 900)

    def test_wide_page_keeps_gutter_boxes_until_cap(self):
        gutters = [[0, 0, 1200, 200], [0, 220, 1200, 400], [0, 420, 1200, 600]]
        boxes = panels_for_page(1200, 800, gutter_boxes=gutters)
        self.assertEqual(boxes, gutters)

    def test_too_many_gutters_are_capped(self):
        gutters = [[0, i * 50, 1000, i * 50 + 40] for i in range(10)]
        boxes = panels_for_page(1000, 800, gutter_boxes=gutters)
        self.assertLessEqual(len(boxes), 4)

    def test_ocr_lines_map_to_containing_panel(self):
        panels = [
            {"panel_index": 0, "page_number": 0, "bbox": [0, 0, 100, 100]},
            {"panel_index": 1, "page_number": 0, "bbox": [0, 100, 100, 200]},
        ]
        lines = [
            ([[10, 10], [20, 10], [20, 20], [10, 20]], "hello"),
            ([[10, 140], [20, 140], [20, 150], [10, 150]], "world"),
        ]
        assigned = assign_lines_to_panels(lines, panels)
        self.assertEqual(assigned[0]["text"], "hello")
        self.assertEqual(assigned[1]["text"], "world")


if __name__ == "__main__":
    unittest.main()
