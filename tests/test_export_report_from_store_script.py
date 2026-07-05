import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.export_report_from_store import export_report_from_store
from scripts.record_review_decision import record_review_decision
from scripts.run_phase_outputs import run_phase_outputs
from src.vyu.authz import Role
from src.vyu.reports import ReportType
from src.vyu.review import ReviewDecision
from src.vyu.storage import ProductionStorage


class ExportReportFromStoreScriptTests(unittest.TestCase):
    def test_export_report_from_store_loads_review_task_and_writes_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "outputs"
            sqlite_path = root / "production.sqlite"
            report_path = root / "exported" / "research_report.md"
            run_phase_outputs(root=root, output_dir=output_dir, sqlite_path=sqlite_path)
            record_review_decision(
                sqlite_db=sqlite_path,
                review_id="review-local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
                user_id="reviewer-1",
                role=Role.REVIEWER,
                decision=ReviewDecision.APPROVE,
                comment="Evidence reviewed for export.",
                decided_at="2026-06-15T00:05:00Z",
            )

            payload = export_report_from_store(
                sqlite_db=sqlite_path,
                output_dir=output_dir,
                review_id="review-local-phase-output-run",
                user_id="reviewer-1",
                role=Role.REVIEWER,
                report_type=ReportType.RESEARCH_REPORT,
                report_output=report_path,
                exported_at="2026-06-15T00:06:00Z",
            )
            storage = ProductionStorage(sqlite_path)
            events = storage.list_audit_events(run_id="local-phase-output-run")
            report_exists = report_path.is_file()
            report_content = report_path.read_text(encoding="utf-8")

        self.assertEqual(200, payload["status_code"])
        self.assertTrue(payload["export"]["allowed"])
        self.assertEqual("export_allowed", payload["export"]["reason"])
        self.assertEqual(str(report_path), payload["report_output"])
        self.assertTrue(report_exists)
        self.assertIn("Research Report", report_content)
        self.assertIn(
            "prompt_injection_decision_recorded",
            [event.event_type for event in events],
        )
        self.assertIn(
            "citation_policy_decision_recorded",
            [event.event_type for event in events],
        )
        self.assertIn(
            "report_export_decision_recorded",
            [event.event_type for event in events],
        )

    def test_export_report_from_store_blocks_pending_review_without_writing_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "outputs"
            sqlite_path = root / "production.sqlite"
            report_path = root / "blocked.md"
            run_phase_outputs(root=root, output_dir=output_dir, sqlite_path=sqlite_path)

            payload = export_report_from_store(
                sqlite_db=sqlite_path,
                output_dir=output_dir,
                review_id="review-local-phase-output-run",
                user_id="reviewer-1",
                role=Role.REVIEWER,
                report_type=ReportType.RESEARCH_REPORT,
                report_output=report_path,
                exported_at="2026-06-15T00:06:00Z",
            )
            storage = ProductionStorage(sqlite_path)
            export_events = storage.list_audit_events(
                run_id="local-phase-output-run",
                event_type="report_export_decision_recorded",
            )

        self.assertEqual(403, payload["status_code"])
        self.assertFalse(payload["export"]["allowed"])
        self.assertEqual("review_required", payload["export"]["reason"])
        self.assertIsNone(payload["report_output"])
        self.assertFalse(report_path.exists())
        self.assertEqual(1, len(export_events))
        self.assertFalse(export_events[0].payload["allowed"])

    def test_export_report_from_store_script_can_be_executed_directly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "outputs"
            sqlite_path = root / "production.sqlite"
            report_path = root / "exported_report.md"
            run_phase_outputs(root=root, output_dir=output_dir, sqlite_path=sqlite_path)
            record_review_decision(
                sqlite_db=sqlite_path,
                review_id="review-local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
                user_id="reviewer-1",
                role=Role.REVIEWER,
                decision=ReviewDecision.APPROVE,
                comment="Evidence reviewed for export.",
                decided_at="2026-06-15T00:05:00Z",
            )
            script_path = (
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "export_report_from_store.py"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--sqlite-db",
                    str(sqlite_path),
                    "--output-dir",
                    str(output_dir),
                    "--review-id",
                    "review-local-phase-output-run",
                    "--user-id",
                    "reviewer-1",
                    "--role",
                    "reviewer",
                    "--report-type",
                    "research_report",
                    "--report-output",
                    str(report_path),
                    "--exported-at",
                    "2026-06-15T00:06:00Z",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            report_exists = report_path.is_file()

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(200, payload["status_code"])
        self.assertTrue(payload["export"]["allowed"])
        self.assertEqual(str(report_path), payload["report_output"])
        self.assertTrue(report_exists)


if __name__ == "__main__":
    unittest.main()
