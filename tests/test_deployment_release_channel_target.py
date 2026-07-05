import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.vyu.deployment import (
    DEPLOYMENT_RELEASE_CHANNEL_EXPORT_SUMMARY_SCHEMA,
    DEPLOYMENT_RELEASE_CHANNEL_TARGET_READINESS_SCHEMA,
    DeploymentReleaseChannelTargetReadinessNote,
    build_deployment_release_channel_target_readiness_note,
    write_deployment_release_channel_target_readiness_note,
)


class DeploymentReleaseChannelTargetReadinessTests(unittest.TestCase):
    def test_target_readiness_is_ready_for_ready_export_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            export_summary_path = _write_export_summary_fixture(root)

            note = build_deployment_release_channel_target_readiness_note(
                export_summary_path=export_summary_path,
                root=root,
                readiness_name="local-release-channel-target-readiness",
                created_at="2026-06-15T04:45:00Z",
            )

        payload = note.to_json()
        checks = {check["name"]: check for check in payload["checks"]}

        self.assertIsInstance(note, DeploymentReleaseChannelTargetReadinessNote)
        self.assertEqual(DEPLOYMENT_RELEASE_CHANNEL_TARGET_READINESS_SCHEMA, payload["schema_version"])
        self.assertEqual("ready", payload["status"])
        self.assertEqual("local-release-channel-target-readiness", payload["readiness_name"])
        self.assertEqual("local_target_family_review_only", payload["target_selection_scope"])
        self.assertIsNone(payload["selected_target_provider"])
        self.assertEqual({}, payload["provider_configuration"])
        self.assertGreaterEqual(payload["summary"]["candidate_target_family_count"], 3)
        self.assertGreaterEqual(payload["summary"]["handoff_checklist_item_count"], 4)
        self.assertEqual(8, payload["summary"]["required_evidence_item_count"])
        self.assertEqual(8, payload["summary"]["present_required_evidence_item_count"])
        self.assertRegex(payload["export_summary"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual("ready", payload["export_summary"]["status"])
        self.assertEqual("vyu-local-serverless-entrypoint", payload["package"]["package_name"])
        self.assertEqual("release-operator", payload["operator"]["id"])
        self.assertEqual("a" * 64, payload["evidence_hashes"]["evidence_index_sha256"])
        self.assertEqual([], payload["blocking_reasons"])
        self.assertTrue(checks["export_summary_status_ready"]["passed"])
        self.assertTrue(checks["export_summary_checks_passed"]["passed"])
        self.assertTrue(checks["export_blocking_reasons_absent"]["passed"])
        self.assertTrue(checks["evidence_index_hash_bound"]["passed"])
        self.assertTrue(checks["no_target_provider_selected"]["passed"])
        self.assertTrue(checks["no_provider_configuration_recorded"]["passed"])

    def test_target_readiness_blocks_when_export_summary_is_blocked_or_has_failed_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            export_summary_path = _write_export_summary_fixture(root, status="blocked", failed_check=True)

            note = build_deployment_release_channel_target_readiness_note(
                export_summary_path=export_summary_path,
                root=root,
                created_at="2026-06-15T04:46:00Z",
            )

        payload = note.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("blocked", payload["status"])
        self.assertFalse(checks["export_summary_status_ready"]["passed"])
        self.assertFalse(checks["export_summary_checks_passed"]["passed"])
        self.assertIn("export_summary_status_ready", payload["blocking_reasons"])

    def test_target_readiness_blocks_when_evidence_index_hash_is_not_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            export_summary_path = _write_export_summary_fixture(root, stale_evidence_index_hash=True)

            note = build_deployment_release_channel_target_readiness_note(
                export_summary_path=export_summary_path,
                root=root,
                created_at="2026-06-15T04:47:00Z",
            )

        payload = note.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("blocked", payload["status"])
        self.assertFalse(checks["evidence_index_hash_bound"]["passed"])

    def test_writer_and_command_write_target_readiness_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            export_summary_path = _write_export_summary_fixture(root)
            output_path = root / "outputs" / "deployment_release_channel_target_readiness.json"

            note = build_deployment_release_channel_target_readiness_note(
                export_summary_path=export_summary_path,
                root=root,
                created_at="2026-06-15T04:48:00Z",
            )
            write_deployment_release_channel_target_readiness_note(note, output_path)
            written_payload = json.loads(output_path.read_text(encoding="utf-8"))

            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/build_deployment_release_channel_target_readiness.py",
                    "--export-summary",
                    "outputs/deployment_release_channel_export_summary.json",
                    "--root",
                    str(root),
                    "--readiness-name",
                    "local-release-channel-target-readiness",
                    "--created-at",
                    "2026-06-15T04:49:00Z",
                    "--target-family",
                    "serverless_function",
                    "--handoff-item",
                    "Select one target family in a future module.",
                    "--output",
                    str(output_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
                check=False,
            )
            command_payload = json.loads(proc.stdout)
            file_payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual("ready", written_payload["status"])
        self.assertEqual(proc.stderr, "")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertEqual("ready", command_payload["status"])
        self.assertEqual(command_payload, file_payload)
        self.assertEqual("2026-06-15T04:49:00Z", file_payload["created_at"])
        self.assertEqual(["serverless_function"], file_payload["candidate_target_families"])
        self.assertEqual(["Select one target family in a future module."], file_payload["handoff_checklist"])


def _write_export_summary_fixture(
    root: Path,
    *,
    status: str = "ready",
    failed_check: bool = False,
    stale_evidence_index_hash: bool = False,
) -> Path:
    outputs = root / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    passed = status == "ready" and not failed_check and not stale_evidence_index_hash
    evidence_index_sha = "a" * 64
    payload = {
        "schema_version": DEPLOYMENT_RELEASE_CHANNEL_EXPORT_SUMMARY_SCHEMA,
        "status": status,
        "created_at": "2026-06-15T04:30:00Z",
        "summary_name": "local-release-channel-evidence-export-summary",
        "evidence_index_path": "outputs/deployment_release_channel_evidence_index.json",
        "evidence_index": {
            "path": "outputs/deployment_release_channel_evidence_index.json",
            "sha256": evidence_index_sha,
            "readable": True,
            "json_valid": True,
            "schema_version": 1,
            "status": "ready",
            "created_at": "2026-06-15T04:15:00Z",
            "index_name": "local-release-channel-evidence-index",
        },
        "publication": {"status": "ready", "sha256": "0" * 64},
        "package": {
            "package_name": "vyu-local-serverless-entrypoint",
            "runtime": "python3.11",
            "handler": "apps.serverless.handler.handler",
        },
        "operator": {"id": "release-operator", "role": "deployment_operator"},
        "decision": {"value": "approve"},
        "evidence_hashes": {
            "evidence_index_sha256": ("b" * 64) if stale_evidence_index_hash else evidence_index_sha,
            "publication_manifest_sha256": "0" * 64,
            "acceptance_record_sha256": "1" * 64,
            "preparation_manifest_sha256": "2" * 64,
            "handoff_inventory_sha256": "3" * 64,
            "handoff_archive_sha256": "4" * 64,
            "release_evidence_summary_sha256": "5" * 64,
            "release_review_decision_sha256": "6" * 64,
            "package_evidence_sha256": "7" * 64,
        },
        "evidence_counts": {
            "required_evidence_item_count": 8,
            "present_required_evidence_item_count": 8,
        },
        "required_evidence_items": [{"name": "publication_manifest", "sha256": "0" * 64}],
        "optional_evidence_items": [{"name": "deployment_release_checklist", "sha256": "8" * 64}],
        "publication_steps": ["Verify accepted release evidence before transfer."],
        "local_only_limits": ["no_artifact_transfer", "no_ci_upload", "no_signing_or_kms"],
        "review_checklist": ["Verify evidence index hash before target selection."],
        "blocking_reasons": [] if status == "ready" and not failed_check else ["export_summary_status_ready"],
        "summary": {
            "passed": 19 if passed else 18,
            "failed": 0 if passed else 1,
            "total": 19,
            "required_evidence_item_count": 8,
            "present_required_evidence_item_count": 8,
            "review_checklist_item_count": 1,
        },
        "checks": [
            {"name": "evidence_index_status_ready", "passed": status == "ready", "detail": status},
            {"name": "evidence_index_hash_bound", "passed": not stale_evidence_index_hash, "detail": "evidence_index.sha256"},
            {"name": "required_evidence_counts_complete", "passed": not failed_check, "detail": "present=8 required=8"},
        ],
    }
    path = outputs / "deployment_release_channel_export_summary.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return Path("outputs/deployment_release_channel_export_summary.json")


if __name__ == "__main__":
    unittest.main()
