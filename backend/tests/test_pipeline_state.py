import unittest

from core.pipeline_state import build_initial_pipeline_state


class PipelineStateTests(unittest.TestCase):
    def test_builds_serializable_worker_state(self):
        state = build_initial_pipeline_state(
            "job-123",
            "job-123/source.pdf",
            manhwa_name="  Example  ",
            genre=" Action ",
            season=" 2 ",
            chapter_number=" 7 ",
            series_context=" Short blurb. ",
        )

        self.assertEqual(state["status"], "UPLOAD_PENDING")
        self.assertEqual(state["job_id"], "job-123")
        self.assertEqual(state["pdf_storage_path"], "job-123/source.pdf")
        self.assertEqual(state["manhwa_name"], "Example")
        self.assertEqual(state["genre"], "Action")
        self.assertEqual(state["season"], "2")
        self.assertEqual(state["chapter_number"], "7")
        self.assertEqual(state["series_context"], "Short blurb.")
        self.assertIsNone(state["error"])

    def test_lists_are_not_shared_between_jobs(self):
        first = build_initial_pipeline_state("first", "first/source.pdf")
        second = build_initial_pipeline_state("second", "second/source.pdf")

        first["page_urls"].append({"path": "first/page.png"})
        self.assertEqual(second["page_urls"], [])


if __name__ == "__main__":
    unittest.main()
