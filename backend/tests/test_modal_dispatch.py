import asyncio
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import BackgroundTasks, HTTPException

from api.routers import jobs, upload
from core import job_launcher, pipeline_runner


class _Response:
    def __init__(self, data):
        self.data = data


class ModalLauncherTests(unittest.TestCase):
    def test_spawn_persists_call_id(self):
        call = types.SimpleNamespace(object_id="fc-123")
        worker = MagicMock()
        worker.spawn.return_value = call
        modal_module = types.SimpleNamespace(
            Function=types.SimpleNamespace(from_name=MagicMock(return_value=worker))
        )
        with (
            patch.dict(sys.modules, {"modal": modal_module}),
            patch.object(job_launcher, "supabase_admin") as database,
        ):
            self.assertEqual(job_launcher.launch_modal_job("job-1"), "fc-123")
        worker.spawn.assert_called_once_with("job-1")
        database.table.return_value.update.assert_called_once_with(
            {"modal_call_id": "fc-123"}
        )

    def test_spawn_failure_is_launch_error(self):
        modal_module = types.SimpleNamespace(
            Function=types.SimpleNamespace(
                from_name=MagicMock(side_effect=RuntimeError("offline"))
            )
        )
        with patch.dict(sys.modules, {"modal": modal_module}):
            with self.assertRaises(job_launcher.JobLaunchError):
                job_launcher.launch_modal_job("job-1")


class PipelineLeaseTests(unittest.TestCase):
    def test_claim_and_heartbeat_use_atomic_rpcs(self):
        database = MagicMock()
        database.rpc.return_value.execute.side_effect = [
            _Response(["CLAIMED"]),
            _Response(["HEARTBEAT"]),
        ]
        with patch.object(pipeline_runner, "supabase_admin", database):
            self.assertEqual(pipeline_runner._claim_job("job-1", "lease-1"), "CLAIMED")
            self.assertTrue(pipeline_runner.heartbeat_job("job-1", "lease-1"))
        self.assertEqual(database.rpc.call_args_list[0].args[0], "claim_processing_job")
        self.assertEqual(database.rpc.call_args_list[1].args[0], "heartbeat_processing_job")

    def test_duplicate_completed_job_is_skipped(self):
        with (
            patch.object(pipeline_runner, "_claim_job", return_value="ALREADY_COMPLETED"),
            patch.object(pipeline_runner, "_load_claimed_job") as load,
        ):
            self.assertEqual(pipeline_runner.process_queued_job("job-1"), {})
        load.assert_not_called()

    def test_runtime_cost_uses_cpu_and_memory(self):
        with (
            patch.object(pipeline_runner.settings, "modal_worker_cpu", 2.0),
            patch.object(pipeline_runner.settings, "modal_worker_memory_mib", 10240),
            patch.object(
                pipeline_runner.settings,
                "modal_cpu_cost_per_core_second_usd",
                0.0000131,
            ),
            patch.object(
                pipeline_runner.settings,
                "modal_memory_cost_per_gib_second_usd",
                0.00000222,
            ),
        ):
            self.assertEqual(pipeline_runner._estimated_compute_cost(1000), 0.0484)

    def test_terminal_status_persists_runtime_and_cost(self):
        database = MagicMock()
        database.rpc.return_value.execute.return_value = _Response(["FINISHED"])
        with (
            patch.object(pipeline_runner, "supabase_admin", database),
            patch.object(pipeline_runner, "_estimated_compute_cost", return_value=0.125),
        ):
            result = pipeline_runner._finish_job(
                "job-1",
                "lease-1",
                "TTS_COMPLETED",
                {"status": "TTS_COMPLETED"},
                123.4567,
            )
        self.assertEqual(result, "FINISHED")
        rpc_name, payload = database.rpc.call_args.args
        self.assertEqual(rpc_name, "finish_processing_job")
        self.assertEqual(payload["p_runtime_seconds"], 123.457)
        self.assertEqual(payload["p_estimated_compute_cost_usd"], 0.125)


class AdmissionTests(unittest.TestCase):
    def _assert_rejected(self, rpc_result: str, expected_detail: str):
        response = _Response([rpc_result])
        current_user = types.SimpleNamespace(sub="firebase-user")
        with patch.object(upload.supabase_admin, "rpc") as rpc:
            rpc.return_value.execute.return_value = response
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(
                    upload.start_job(
                        "00000000-0000-0000-0000-000000000001",
                        BackgroundTasks(),
                        current_user,
                    )
                )
        self.assertEqual(caught.exception.status_code, 429)
        self.assertIn(expected_detail, caught.exception.detail)

    def test_daily_quota_rejection(self):
        self._assert_rejected("DAILY_LIMIT", "daily")

    def test_budget_rejection(self):
        self._assert_rejected("BUDGET_LIMIT", "compute safety")


class RequirementsFlattenTests(unittest.TestCase):
    def test_worker_includes_are_inlined(self):
        from modal_app import flatten_requirements

        backend = Path(__file__).resolve().parents[1]
        flattened = Path(flatten_requirements(backend / "requirements-worker.txt"))
        text = flattened.read_text(encoding="utf-8")
        self.assertNotIn("-r ", text)
        self.assertIn("fastapi", text)
        self.assertIn("paddleocr==2.7.3", text)
        flattened.unlink(missing_ok=True)

    def test_ocr_bootstrap_is_importable_without_requirements_files(self):
        import ocr_bootstrap

        self.assertTrue(callable(ocr_bootstrap.download_ocr_models))

    def test_modal_app_does_not_import_ocr_bootstrap_at_module_level(self):
        source = (Path(__file__).resolve().parents[1] / "modal_app.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("    from ocr_bootstrap import download_ocr_models", source)
        self.assertFalse(source.lstrip().startswith("from ocr_bootstrap import"))


class MigrationContractTests(unittest.TestCase):
    def test_migration_has_atomic_claim_and_stale_recovery(self):
        migration = (
            Path(__file__).parents[1]
            / "db"
            / "migrations"
            / "003_modal_dispatch_and_budget.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("for update", migration.lower())
        self.assertIn("claim_processing_job", migration)
        self.assertIn("heartbeat_processing_job", migration)
        self.assertIn("recover_stale_processing_jobs", migration)
        self.assertIn("perform * from public.recover_stale_processing_jobs()", migration)
        self.assertIn("BUDGET_LIMIT", migration)
        self.assertIn("status not in ('TTS_COMPLETED', 'FAILED')", migration)


class LeaseProgressTests(unittest.TestCase):
    def test_progress_does_not_overwrite_processing_status(self):
        fake_graph = types.ModuleType("langgraph")
        fake_graph.graph = types.SimpleNamespace(StateGraph=object, END=object)
        database = MagicMock()
        database.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = _Response(
            [{"state_json": {"job_id": "job-1"}}]
        )
        with patch.dict(sys.modules, {"langgraph": fake_graph, "langgraph.graph": fake_graph.graph}):
            from core import langgraph_app
            with patch.object(langgraph_app, "supabase_admin", database):
                langgraph_app.update_job_status("job-1", "EXTRACTED")
                langgraph_app.update_job_status("job-1", "TTS_COMPLETED")
        updates = [
            call.args[0]
            for call in database.table.return_value.update.call_args_list
        ]
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0]["state_json"]["status"], "EXTRACTED")
        self.assertNotIn("status", updates[0])

    def test_job_status_exposes_phase_while_leased(self):
        row = {
            "status": "PROCESSING",
            "state_json": {"status": "PANELS_DETECTED"},
        }
        self.assertEqual(jobs.public_job_status(row)["status"], "PANELS_DETECTED")
        completed = {
            "status": "PROCESSING",
            "state_json": {"status": "TTS_COMPLETED"},
        }
        self.assertEqual(jobs.public_job_status(completed)["status"], "PROCESSING")


if __name__ == "__main__":
    unittest.main()
