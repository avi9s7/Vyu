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


class IncidentRecoveryDrillTests(unittest.TestCase):
    def test_drill_records_attention_state_backup_restore_and_restored_inspection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            backup_path = root / "drill_backup.json"
            restored_sqlite_path = root / "restored_drill.sqlite"
            output_dir = root / "outputs"
            run_phase_outputs(root=root, output_dir=output_dir, sqlite_path=sqlite_path)
            module = _drill_module()

            payload = module.run_incident_recovery_drill(
                sqlite_db=sqlite_path,
                backup_path=backup_path,
                restored_sqlite_db=restored_sqlite_path,
                run_id="local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
            )
            backup_exists = backup_path.is_file()
            restored_sqlite_exists = restored_sqlite_path.is_file()

        self.assertEqual("pass", payload["status"])
        self.assertTrue(payload["incident"]["detected"])
        self.assertIn("review_pending", payload["incident"]["attention_reasons"])
        self.assertIn("readiness_missing", payload["incident"]["attention_reasons"])
        self.assertEqual("exported", payload["backup"]["status"])
        self.assertEqual("restored", payload["restore"]["status"])
        self.assertTrue(payload["restored_scope_inspection"]["inspectable"])
        self.assertEqual(
            "review-local-phase-output-run",
            payload["restored_scope_inspection"]["review_task_ids"][0],
        )
        self.assertEqual("attention", payload["restored_observability"]["status"])
        self.assertTrue(backup_exists)
        self.assertTrue(restored_sqlite_exists)

    def test_drill_preserves_ok_status_after_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            backup_path = root / "drill_backup.json"
            restored_sqlite_path = root / "restored_drill.sqlite"
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
            module = _drill_module()

            payload = module.run_incident_recovery_drill(
                sqlite_db=sqlite_path,
                backup_path=backup_path,
                restored_sqlite_db=restored_sqlite_path,
                run_id="local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
            )

        self.assertEqual("pass", payload["status"])
        self.assertFalse(payload["incident"]["detected"])
        self.assertEqual([], payload["incident"]["attention_reasons"])
        self.assertGreaterEqual(payload["backup"]["counts"]["readiness_check_result_count"], 1)
        self.assertEqual("ok", payload["restored_observability"]["status"])
        self.assertEqual("pass", payload["restored_observability"]["readiness"]["latest_status"])

    def test_drill_can_rerun_with_same_restored_sqlite_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            backup_path = root / "drill_backup.json"
            restored_sqlite_path = root / "restored_drill.sqlite"
            output_dir = root / "outputs"
            run_phase_outputs(root=root, output_dir=output_dir, sqlite_path=sqlite_path)
            module = _drill_module()

            first = module.run_incident_recovery_drill(
                sqlite_db=sqlite_path,
                backup_path=backup_path,
                restored_sqlite_db=restored_sqlite_path,
                run_id="local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
            )
            second = module.run_incident_recovery_drill(
                sqlite_db=sqlite_path,
                backup_path=backup_path,
                restored_sqlite_db=restored_sqlite_path,
                run_id="local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
            )

        self.assertEqual("pass", first["status"])
        self.assertEqual("pass", second["status"])
        self.assertTrue(second["restore"]["counts_match_backup"])

    def test_drill_command_prints_json_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            backup_path = root / "drill_backup.json"
            restored_sqlite_path = root / "restored_drill.sqlite"
            output_dir = root / "outputs"
            run_phase_outputs(root=root, output_dir=output_dir, sqlite_path=sqlite_path)
            script_path = (
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "run_incident_recovery_drill.py"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--sqlite-db",
                    str(sqlite_path),
                    "--backup",
                    str(backup_path),
                    "--restored-sqlite-db",
                    str(restored_sqlite_path),
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
        self.assertEqual("pass", payload["status"])
        self.assertTrue(payload["incident"]["detected"])
        self.assertEqual("restored", payload["restore"]["status"])

    def test_drill_command_rejects_wrong_scope_before_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            backup_path = root / "drill_backup.json"
            restored_sqlite_path = root / "restored_drill.sqlite"
            output_dir = root / "outputs"
            run_phase_outputs(root=root, output_dir=output_dir, sqlite_path=sqlite_path)
            script_path = (
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "run_incident_recovery_drill.py"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--sqlite-db",
                    str(sqlite_path),
                    "--backup",
                    str(backup_path),
                    "--restored-sqlite-db",
                    str(restored_sqlite_path),
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
        self.assertFalse(backup_path.exists())
        self.assertFalse(restored_sqlite_path.exists())


def _drill_module():
    try:
        return importlib.import_module("scripts.run_incident_recovery_drill")
    except ModuleNotFoundError as exc:
        raise AssertionError("incident recovery drill script is not implemented") from exc


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
