import importlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.check_production_readiness import check_production_readiness
from scripts.export_report_from_store import export_report_from_store
from scripts.record_review_decision import record_review_decision
from scripts.run_phase_outputs import run_phase_outputs
from src.vyu.authz import Role
from src.vyu.reports import ReportType
from src.vyu.review import ReviewDecision
from src.vyu.sources import ProductionSourceRecord, SourceRegistry


class ProductionObservabilityTests(unittest.TestCase):
    def test_observability_snapshot_summarizes_review_export_connector_and_readiness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            output_dir = root / "outputs"
            registry_path = root / "source_registry.json"
            _write_approved_registry(registry_path)
            run_phase_outputs(
                root=root,
                output_dir=output_dir,
                source_registry_path=registry_path,
                sqlite_path=sqlite_path,
            )
            _approve_review_export_and_check_readiness(sqlite_path, output_dir)
            module = _observability_module()

            payload = module.summarize_production_observability(
                sqlite_db=sqlite_path,
                run_id="local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
            )

        self.assertEqual("local-phase-output-run", payload["run_id"])
        self.assertEqual("local_tenant", payload["tenant_id"])
        self.assertEqual("local_workspace", payload["workspace_id"])
        self.assertEqual("ok", payload["status"])
        self.assertEqual("pass", payload["readiness"]["latest_status"])
        self.assertEqual([], payload["readiness"]["latest_failed_checks"])
        self.assertEqual({"approved": 1}, payload["review"]["status_counts"])
        self.assertEqual(1, payload["report_export"]["allowed_count"])
        self.assertEqual(0, payload["report_export"]["blocked_count"])
        self.assertEqual("export_allowed", payload["report_export"]["latest_reason"])
        self.assertEqual({"ok": 1}, payload["connectors"]["health_status_counts"])
        self.assertEqual({"ok": 1}, payload["connectors"]["validation_status_counts"])
        self.assertGreaterEqual(payload["audit_events"]["total_count"], 10)
        self.assertIn(
            "readiness_check_result_recorded",
            payload["audit_events"]["event_type_counts"],
        )

    def test_observability_snapshot_marks_pending_review_run_for_attention(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            output_dir = root / "outputs"
            registry_path = root / "source_registry.json"
            _write_approved_registry(registry_path)
            run_phase_outputs(
                root=root,
                output_dir=output_dir,
                source_registry_path=registry_path,
                sqlite_path=sqlite_path,
            )
            module = _observability_module()

            payload = module.summarize_production_observability(
                sqlite_db=sqlite_path,
                run_id="local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
            )

        self.assertEqual("attention", payload["status"])
        self.assertEqual({"pending": 1}, payload["review"]["status_counts"])
        self.assertEqual(0, payload["report_export"]["allowed_count"])
        self.assertIn("review_pending", payload["attention_reasons"])
        self.assertIn("readiness_missing", payload["attention_reasons"])
        self.assertIn("allowed_report_export_missing", payload["attention_reasons"])

    def test_observability_command_prints_scoped_json_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            output_dir = root / "outputs"
            registry_path = root / "source_registry.json"
            _write_approved_registry(registry_path)
            run_phase_outputs(
                root=root,
                output_dir=output_dir,
                source_registry_path=registry_path,
                sqlite_path=sqlite_path,
            )
            _approve_review_export_and_check_readiness(sqlite_path, output_dir)
            script_path = (
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "summarize_production_observability.py"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--sqlite-db",
                    str(sqlite_path),
                    "--run-id",
                    "local-phase-output-run",
                    "--tenant-id",
                    "local_tenant",
                    "--workspace-id",
                    "local_workspace",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("ok", payload["status"])
        self.assertEqual("pass", payload["readiness"]["latest_status"])

    def test_observability_command_rejects_wrong_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            output_dir = root / "outputs"
            run_phase_outputs(root=root, output_dir=output_dir, sqlite_path=sqlite_path)
            script_path = (
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "summarize_production_observability.py"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--sqlite-db",
                    str(sqlite_path),
                    "--run-id",
                    "local-phase-output-run",
                    "--tenant-id",
                    "other_tenant",
                    "--workspace-id",
                    "local_workspace",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("outside the requested tenant/workspace scope", result.stderr)


def _observability_module():
    try:
        return importlib.import_module("scripts.summarize_production_observability")
    except ModuleNotFoundError as exc:
        raise AssertionError("observability snapshot script is not implemented") from exc


def _approve_review_export_and_check_readiness(sqlite_path: Path, output_dir: Path) -> None:
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
    export_report_from_store(
        sqlite_db=sqlite_path,
        output_dir=output_dir,
        review_id="review-local-phase-output-run",
        user_id="reviewer-1",
        role=Role.REVIEWER,
        report_type=ReportType.RESEARCH_REPORT,
        report_output=output_dir / "exported" / "research_report.md",
        exported_at="2026-06-15T00:06:00Z",
    )
    check_production_readiness(
        sqlite_db=sqlite_path,
        artifact_manifest_path=output_dir / "artifact_manifest.json",
        run_summary_path=output_dir / "run_summary.json",
        run_id="local-phase-output-run",
        tenant_id="local_tenant",
        workspace_id="local_workspace",
    )


def _write_approved_registry(path: Path) -> None:
    SourceRegistry(
        [
            _approved_source("dummy_corpus"),
            _approved_source("golden_questions"),
        ]
    ).write(path)


def _approved_source(source_id: str) -> ProductionSourceRecord:
    return ProductionSourceRecord(
        source_id=source_id,
        display_name=source_id.replace("_", " ").title(),
        source_type="public_literature",
        owner="Vyu",
        license_or_terms="Synthetic local fixture",
        allowed_uses=["artifact_generation"],
        approval_status="approved",
        approved_by="production-review-board",
        approved_at="2026-06-14T00:00:00Z",
    )


if __name__ == "__main__":
    unittest.main()
