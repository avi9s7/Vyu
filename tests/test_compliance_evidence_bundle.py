import importlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.backup_production_store import export_production_backup
from scripts.check_production_readiness import check_production_readiness
from scripts.export_report_from_store import export_report_from_store
from scripts.record_compliance_attestation import record_compliance_attestation
from scripts.record_review_decision import record_review_decision
from scripts.run_incident_recovery_drill import run_incident_recovery_drill
from scripts.run_phase_outputs import run_phase_outputs
from src.vyu.authz import Role
from src.vyu.reports import ReportType
from src.vyu.review import ReviewDecision
from src.vyu.sources import ProductionSourceRecord, SourceRegistry


class ComplianceEvidenceBundleTests(unittest.TestCase):
    def test_bundle_packages_ready_pilot_review_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            output_dir = root / "outputs"
            registry_path = root / "source_registry.json"
            backup_path = root / "production_backup.json"
            drill_backup_path = root / "drill_backup.json"
            drill_restore_path = root / "drill_restored.sqlite"
            drill_json_path = root / "drill.json"
            bundle_path = root / "compliance_bundle.json"
            _write_approved_registry(registry_path)
            run_phase_outputs(
                root=root,
                output_dir=output_dir,
                source_registry_path=registry_path,
                sqlite_path=sqlite_path,
            )
            _approve_review_export_and_check_readiness(sqlite_path, output_dir)
            export_production_backup(sqlite_path, backup_path)
            drill_payload = run_incident_recovery_drill(
                sqlite_db=sqlite_path,
                backup_path=drill_backup_path,
                restored_sqlite_db=drill_restore_path,
                run_id="local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
            )
            drill_json_path.write_text(
                json.dumps(drill_payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            module = _bundle_module()

            payload = module.build_compliance_evidence_bundle(
                sqlite_db=sqlite_path,
                artifact_manifest_path=output_dir / "artifact_manifest.json",
                source_registry_path=registry_path,
                backup_path=backup_path,
                drill_json_path=drill_json_path,
                output_path=bundle_path,
                run_id="local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
            )
            written = json.loads(bundle_path.read_text(encoding="utf-8"))

        self.assertEqual(payload, written)
        self.assertEqual("ready_for_pilot_review", payload["status"])
        self.assertEqual([], payload["attention_reasons"])
        self.assertEqual("pass", payload["readiness"]["latest_status"])
        self.assertEqual("ok", payload["observability"]["status"])
        self.assertEqual("pass", payload["incident_recovery_drill"]["status"])
        self.assertTrue(payload["incident_recovery_drill"]["restore_counts_match_backup"])
        self.assertEqual(2, payload["source_approval"]["approved_source_count"])
        self.assertEqual(
            ["dummy_corpus", "golden_questions"],
            payload["source_approval"]["approved_source_ids"],
        )
        self.assertGreaterEqual(len(payload["policy_documents"]), 10)
        self.assertTrue(all(item["present"] for item in payload["policy_documents"]))
        self.assertGreater(payload["backup"]["counts"]["audit_event_count"], 0)
        self.assertEqual(1, payload["scoped_inspection"]["review_task_count"])

    def test_bundle_marks_attention_when_review_and_readiness_are_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            output_dir = root / "outputs"
            registry_path = root / "source_registry.json"
            backup_path = root / "production_backup.json"
            drill_backup_path = root / "drill_backup.json"
            drill_restore_path = root / "drill_restored.sqlite"
            drill_json_path = root / "drill.json"
            bundle_path = root / "compliance_bundle.json"
            _write_approved_registry(registry_path)
            run_phase_outputs(
                root=root,
                output_dir=output_dir,
                source_registry_path=registry_path,
                sqlite_path=sqlite_path,
            )
            export_production_backup(sqlite_path, backup_path)
            drill_payload = run_incident_recovery_drill(
                sqlite_db=sqlite_path,
                backup_path=drill_backup_path,
                restored_sqlite_db=drill_restore_path,
                run_id="local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
            )
            drill_json_path.write_text(
                json.dumps(drill_payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            module = _bundle_module()

            payload = module.build_compliance_evidence_bundle(
                sqlite_db=sqlite_path,
                artifact_manifest_path=output_dir / "artifact_manifest.json",
                source_registry_path=registry_path,
                backup_path=backup_path,
                drill_json_path=drill_json_path,
                output_path=bundle_path,
                run_id="local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
            )

        self.assertEqual("attention", payload["status"])
        self.assertIn("readiness_missing", payload["attention_reasons"])
        self.assertIn("review_pending", payload["attention_reasons"])
        self.assertIn("allowed_report_export_missing", payload["attention_reasons"])
        self.assertEqual("attention", payload["observability"]["status"])
        self.assertTrue(payload["incident_recovery_drill"]["incident_detected"])

    def test_bundle_summarizes_matching_attestations_when_provided(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            output_dir = root / "outputs"
            registry_path = root / "source_registry.json"
            backup_path = root / "production_backup.json"
            drill_backup_path = root / "drill_backup.json"
            drill_restore_path = root / "drill_restored.sqlite"
            drill_json_path = root / "drill.json"
            bundle_path = root / "compliance_bundle.json"
            attested_bundle_path = root / "attested_compliance_bundle.json"
            attestations_path = root / "compliance_attestations.jsonl"
            _write_approved_registry(registry_path)
            run_phase_outputs(
                root=root,
                output_dir=output_dir,
                source_registry_path=registry_path,
                sqlite_path=sqlite_path,
            )
            _approve_review_export_and_check_readiness(sqlite_path, output_dir)
            export_production_backup(sqlite_path, backup_path)
            drill_payload = run_incident_recovery_drill(
                sqlite_db=sqlite_path,
                backup_path=drill_backup_path,
                restored_sqlite_db=drill_restore_path,
                run_id="local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
            )
            drill_json_path.write_text(
                json.dumps(drill_payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            module = _bundle_module()
            module.build_compliance_evidence_bundle(
                sqlite_db=sqlite_path,
                artifact_manifest_path=output_dir / "artifact_manifest.json",
                source_registry_path=registry_path,
                backup_path=backup_path,
                drill_json_path=drill_json_path,
                output_path=bundle_path,
                run_id="local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
            )
            record_compliance_attestation(
                bundle_path=bundle_path,
                attestations_path=attestations_path,
                run_id="local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
                approver_id="privacy-owner",
                approver_role="privacy_owner",
                decision="approve",
                comment="Privacy evidence reviewed for pilot intake.",
                attested_at="2026-06-15T00:30:00Z",
            )

            payload = module.build_compliance_evidence_bundle(
                sqlite_db=sqlite_path,
                artifact_manifest_path=output_dir / "artifact_manifest.json",
                source_registry_path=registry_path,
                backup_path=backup_path,
                drill_json_path=drill_json_path,
                output_path=attested_bundle_path,
                run_id="local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
                attestations_path=attestations_path,
            )

        self.assertEqual("ready_for_pilot_review", payload["status"])
        self.assertEqual(str(attestations_path), payload["attestations"]["path"])
        self.assertEqual(1, payload["attestations"]["record_count"])
        self.assertEqual({"approve": 1}, payload["attestations"]["decision_counts"])
        self.assertEqual(["privacy_owner"], payload["attestations"]["approver_roles"])
        self.assertEqual("approve", payload["attestations"]["latest_decision"])

    def test_bundle_command_prints_and_writes_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            output_dir = root / "outputs"
            registry_path = root / "source_registry.json"
            backup_path = root / "production_backup.json"
            drill_backup_path = root / "drill_backup.json"
            drill_restore_path = root / "drill_restored.sqlite"
            drill_json_path = root / "drill.json"
            bundle_path = root / "compliance_bundle.json"
            _write_approved_registry(registry_path)
            run_phase_outputs(
                root=root,
                output_dir=output_dir,
                source_registry_path=registry_path,
                sqlite_path=sqlite_path,
            )
            _approve_review_export_and_check_readiness(sqlite_path, output_dir)
            export_production_backup(sqlite_path, backup_path)
            drill_payload = run_incident_recovery_drill(
                sqlite_db=sqlite_path,
                backup_path=drill_backup_path,
                restored_sqlite_db=drill_restore_path,
                run_id="local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
            )
            drill_json_path.write_text(
                json.dumps(drill_payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            script_path = (
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "build_compliance_evidence_bundle.py"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--sqlite-db",
                    str(sqlite_path),
                    "--artifact-manifest",
                    str(output_dir / "artifact_manifest.json"),
                    "--source-registry",
                    str(registry_path),
                    "--backup",
                    str(backup_path),
                    "--drill-json",
                    str(drill_json_path),
                    "--output",
                    str(bundle_path),
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
            written = (
                json.loads(bundle_path.read_text(encoding="utf-8"))
                if bundle_path.is_file()
                else None
            )

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload, written)
        self.assertEqual("ready_for_pilot_review", payload["status"])

    def test_bundle_command_rejects_wrong_scope_before_writing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            output_dir = root / "outputs"
            registry_path = root / "source_registry.json"
            backup_path = root / "production_backup.json"
            drill_json_path = root / "drill.json"
            bundle_path = root / "compliance_bundle.json"
            _write_approved_registry(registry_path)
            run_phase_outputs(
                root=root,
                output_dir=output_dir,
                source_registry_path=registry_path,
                sqlite_path=sqlite_path,
            )
            export_production_backup(sqlite_path, backup_path)
            drill_json_path.write_text(
                json.dumps({"status": "pass"}, sort_keys=True),
                encoding="utf-8",
            )
            script_path = (
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "build_compliance_evidence_bundle.py"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--sqlite-db",
                    str(sqlite_path),
                    "--artifact-manifest",
                    str(output_dir / "artifact_manifest.json"),
                    "--source-registry",
                    str(registry_path),
                    "--backup",
                    str(backup_path),
                    "--drill-json",
                    str(drill_json_path),
                    "--output",
                    str(bundle_path),
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
        self.assertFalse(bundle_path.exists())


def _bundle_module():
    try:
        return importlib.import_module("scripts.build_compliance_evidence_bundle")
    except ModuleNotFoundError as exc:
        raise AssertionError("compliance evidence bundle script is not implemented") from exc


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
