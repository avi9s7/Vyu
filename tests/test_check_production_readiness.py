import json
import subprocess
import sys
import tempfile
import unittest
import sqlite3
from pathlib import Path

from scripts.export_report_from_store import export_report_from_store
from scripts.record_review_decision import record_review_decision
from scripts.run_phase_outputs import run_phase_outputs
from src.vyu.authz import Role
from src.vyu.reports import ReportType
from src.vyu.review import ReviewDecision
from src.vyu.sources import ProductionSourceRecord, SourceRegistry
from src.vyu.storage import ProductionScope, ProductionStorage


class CheckProductionReadinessTests(unittest.TestCase):
    def test_check_command_passes_for_generated_outputs(self):
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
            _approve_review_and_export_report(sqlite_path, output_dir)
            script_path = (
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "check_production_readiness.py"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--sqlite-db",
                    str(sqlite_path),
                    "--artifact-manifest",
                    str(output_dir / "artifact_manifest.json"),
                    "--run-summary",
                    str(output_dir / "run_summary.json"),
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
            payload = json.loads(result.stdout)
            storage = ProductionStorage(sqlite_path)
            readiness_results = storage.list_readiness_check_results_for_scope(
                ProductionScope(
                    tenant_id="local_tenant",
                    workspace_id="local_workspace",
                ),
                run_id="local-phase-output-run",
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("pass", payload["status"])
        self.assertEqual(
            {
                "scoped_manifest_access",
                "schema_version_current",
                "migration_history_present",
                "approved_sources_present",
                "artifact_checksums_present",
                "artifact_checksums_match_files",
                "evaluation_run_present",
                "audit_events_present",
                "review_approval_present",
                "report_export_audit_present",
                "connector_health_present",
                "connector_validation_present",
                "evidence_objects_present",
                "retrieval_index_current",
                "retrieval_run_present",
                "research_memory_present",
                "evidence_methodology_run_present",
                "evidence_methodology_assessments_present",
                "evidence_methodology_scores_present",
                "external_evidence_grading_connector_present",
                "production_trust_score_present",
                "production_trust_score_bounded",
                "production_governance_box_present",
                "production_governance_box_audit_export_status_present",
                "external_governance_connector_present",
                "run_summary_consistent",
                "wrong_scope_rejected",
            },
            {check["name"] for check in payload["checks"]},
        )
        self.assertTrue(all(check["passed"] for check in payload["checks"]))
        self.assertEqual(1, len(readiness_results))
        self.assertEqual("pass", readiness_results[0].status)
        self.assertEqual(payload["checks"], list(readiness_results[0].checks))

    def test_check_command_fails_when_manifest_checksum_is_missing(self):
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
            _approve_review_and_export_report(sqlite_path, output_dir)
            manifest_path = output_dir / "artifact_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["artifacts"][0]["checksum_sha256"] = ""
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            script_path = (
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "check_production_readiness.py"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--sqlite-db",
                    str(sqlite_path),
                    "--artifact-manifest",
                    str(manifest_path),
                    "--run-summary",
                    str(output_dir / "run_summary.json"),
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
            payload = json.loads(result.stdout)
            storage = ProductionStorage(sqlite_path)
            readiness_results = storage.list_readiness_check_results_for_scope(
                ProductionScope(
                    tenant_id="local_tenant",
                    workspace_id="local_workspace",
                ),
                run_id="local-phase-output-run",
            )

        self.assertEqual(1, result.returncode)
        self.assertEqual("fail", payload["status"])
        failed = [check for check in payload["checks"] if not check["passed"]]
        self.assertEqual(["artifact_checksums_present"], [check["name"] for check in failed])
        self.assertEqual(1, len(readiness_results))
        self.assertEqual("fail", readiness_results[0].status)
        self.assertEqual(("artifact_checksums_present",), readiness_results[0].failed_checks)

    def test_check_command_fails_when_connector_validation_is_missing(self):
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
            _approve_review_and_export_report(sqlite_path, output_dir)
            connection = sqlite3.connect(sqlite_path)
            try:
                connection.execute("delete from staged_connector_validations")
                connection.commit()
            finally:
                connection.close()
            script_path = (
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "check_production_readiness.py"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--sqlite-db",
                    str(sqlite_path),
                    "--artifact-manifest",
                    str(output_dir / "artifact_manifest.json"),
                    "--run-summary",
                    str(output_dir / "run_summary.json"),
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

        self.assertEqual(1, result.returncode)
        payload = json.loads(result.stdout)
        failed = [check for check in payload["checks"] if not check["passed"]]
        self.assertEqual(["connector_validation_present"], [check["name"] for check in failed])

    def test_check_command_fails_when_review_is_not_approved_for_export(self):
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
            export_report_from_store(
                sqlite_db=sqlite_path,
                output_dir=output_dir,
                review_id="review-local-phase-output-run",
                user_id="reviewer-1",
                role=Role.REVIEWER,
                report_type=ReportType.RESEARCH_REPORT,
                report_output=root / "blocked.md",
                exported_at="2026-06-15T00:06:00Z",
            )
            script_path = (
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "check_production_readiness.py"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--sqlite-db",
                    str(sqlite_path),
                    "--artifact-manifest",
                    str(output_dir / "artifact_manifest.json"),
                    "--run-summary",
                    str(output_dir / "run_summary.json"),
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

        self.assertEqual(1, result.returncode)
        payload = json.loads(result.stdout)
        failed = [check for check in payload["checks"] if not check["passed"]]
        self.assertEqual(
            ["review_approval_present", "report_export_audit_present"],
            [check["name"] for check in failed],
        )

    def test_check_command_fails_when_report_export_audit_is_missing(self):
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
                / "check_production_readiness.py"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--sqlite-db",
                    str(sqlite_path),
                    "--artifact-manifest",
                    str(output_dir / "artifact_manifest.json"),
                    "--run-summary",
                    str(output_dir / "run_summary.json"),
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

        self.assertEqual(1, result.returncode)
        payload = json.loads(result.stdout)
        failed = [check for check in payload["checks"] if not check["passed"]]
        self.assertEqual(
            ["report_export_audit_present"],
            [check["name"] for check in failed],
        )


def _write_approved_registry(path: Path) -> None:
    SourceRegistry(
        [
            _approved_source("dummy_corpus"),
            _approved_source("golden_questions"),
        ]
    ).write(path)


def _approve_review_and_export_report(sqlite_path: Path, output_dir: Path) -> None:
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
