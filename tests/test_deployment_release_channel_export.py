import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.vyu.deployment import (
    DEPLOYMENT_RELEASE_CHANNEL_EVIDENCE_INDEX_SCHEMA,
    DEPLOYMENT_RELEASE_CHANNEL_EXPORT_SUMMARY_SCHEMA,
    DeploymentReleaseChannelExportSummary,
    build_deployment_release_channel_export_summary,
    write_deployment_release_channel_export_summary,
)


class DeploymentReleaseChannelExportSummaryTests(unittest.TestCase):
    def test_export_summary_is_ready_for_ready_evidence_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = _write_evidence_index_fixture(root)

            summary = build_deployment_release_channel_export_summary(
                evidence_index_path=index_path,
                root=root,
                summary_name="local-release-channel-evidence-export-summary",
                created_at="2026-06-15T04:30:00Z",
            )

        payload = summary.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        hashes = payload["evidence_hashes"]

        self.assertIsInstance(summary, DeploymentReleaseChannelExportSummary)
        self.assertEqual(DEPLOYMENT_RELEASE_CHANNEL_EXPORT_SUMMARY_SCHEMA, payload["schema_version"])
        self.assertEqual("ready", payload["status"])
        self.assertEqual("local-release-channel-evidence-export-summary", payload["summary_name"])
        self.assertRegex(payload["evidence_index"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual("ready", payload["evidence_index"]["status"])
        self.assertEqual("ready", payload["publication"]["status"])
        self.assertEqual("vyu-local-serverless-entrypoint", payload["package"]["package_name"])
        self.assertEqual("release-operator", payload["operator"]["id"])
        self.assertEqual("approve", payload["decision"]["value"])
        self.assertEqual("1" * 64, hashes["acceptance_record_sha256"])
        self.assertEqual("2" * 64, hashes["preparation_manifest_sha256"])
        self.assertEqual("3" * 64, hashes["handoff_inventory_sha256"])
        self.assertEqual("4" * 64, hashes["handoff_archive_sha256"])
        self.assertEqual("5" * 64, hashes["release_evidence_summary_sha256"])
        self.assertEqual("6" * 64, hashes["release_review_decision_sha256"])
        self.assertEqual("7" * 64, hashes["package_evidence_sha256"])
        self.assertEqual(8, payload["summary"]["required_evidence_item_count"])
        self.assertEqual(8, payload["summary"]["present_required_evidence_item_count"])
        self.assertGreaterEqual(payload["summary"]["review_checklist_item_count"], 4)
        self.assertEqual([], payload["blocking_reasons"])
        self.assertTrue(checks["evidence_index_status_ready"]["passed"])
        self.assertTrue(checks["evidence_index_checks_passed"]["passed"])
        self.assertTrue(checks["handoff_archive_hash_bound"]["passed"])
        self.assertTrue(checks["required_evidence_counts_complete"]["passed"])
        self.assertTrue(checks["review_checklist_present"]["passed"])

    def test_export_summary_blocks_when_evidence_index_is_blocked_or_has_failed_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = _write_evidence_index_fixture(root, status="blocked", failed_check=True)

            summary = build_deployment_release_channel_export_summary(
                evidence_index_path=index_path,
                root=root,
                created_at="2026-06-15T04:31:00Z",
            )

        payload = summary.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("blocked", payload["status"])
        self.assertIn("evidence_index_status_ready", payload["blocking_reasons"])
        self.assertFalse(checks["evidence_index_status_ready"]["passed"])
        self.assertFalse(checks["evidence_index_checks_passed"]["passed"])

    def test_export_summary_blocks_when_required_evidence_counts_are_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = _write_evidence_index_fixture(root, missing_required_hash=True)

            summary = build_deployment_release_channel_export_summary(
                evidence_index_path=index_path,
                root=root,
                created_at="2026-06-15T04:32:00Z",
            )

        payload = summary.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("blocked", payload["status"])
        self.assertFalse(checks["handoff_inventory_sha256_present"]["passed"])
        self.assertFalse(checks["required_evidence_counts_complete"]["passed"])

    def test_writer_and_command_write_export_summary_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = _write_evidence_index_fixture(root)
            output_path = root / "outputs" / "deployment_release_channel_export_summary.json"

            summary = build_deployment_release_channel_export_summary(
                evidence_index_path=index_path,
                root=root,
                created_at="2026-06-15T04:33:00Z",
            )
            write_deployment_release_channel_export_summary(summary, output_path)
            written_payload = json.loads(output_path.read_text(encoding="utf-8"))

            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/build_deployment_release_channel_export_summary.py",
                    "--evidence-index",
                    "outputs/deployment_release_channel_evidence_index.json",
                    "--root",
                    str(root),
                    "--summary-name",
                    "local-release-channel-evidence-export-summary",
                    "--created-at",
                    "2026-06-15T04:34:00Z",
                    "--review-item",
                    "Verify evidence index hash before target selection.",
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
        self.assertEqual("2026-06-15T04:34:00Z", file_payload["created_at"])
        self.assertEqual(["Verify evidence index hash before target selection."], file_payload["review_checklist"])


def _write_evidence_index_fixture(
    root: Path,
    *,
    status: str = "ready",
    failed_check: bool = False,
    missing_required_hash: bool = False,
) -> Path:
    outputs = root / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    evidence_items = [
        _item("publication_manifest", "release_channel_publication_manifest", "0" * 64, "publication_file.sha256"),
        _item("acceptance_record", "release_channel_acceptance_record", "1" * 64, "acceptance.sha256"),
        _item("preparation_manifest", "release_channel_preparation_manifest", "2" * 64, "preparation.sha256"),
        _item("handoff_inventory", "release_handoff_inventory", None if missing_required_hash else "3" * 64, "preparation_inventory_sha256"),
        _item("handoff_archive", "release_handoff_archive", "4" * 64, "preparation_archive.sha256", expected_sha256="4" * 64, hash_matches_expected=True),
        _item("release_evidence_summary", "release_evidence_summary", "5" * 64, "preparation_artifact_hashes.release_evidence_summary_sha256"),
        _item("release_review_decision", "release_review_decision", "6" * 64, "preparation_artifact_hashes.release_review_decision_sha256"),
        _item("package_evidence", "deployment_package_evidence", "7" * 64, "preparation_artifact_hashes.package_evidence_sha256"),
        _item("deployment_release_checklist", "deployment_release_checklist", "8" * 64, "preparation_artifact_hashes.release_checklist_sha256", required=False),
    ]
    passed = status == "ready" and not failed_check and not missing_required_hash
    payload = {
        "schema_version": DEPLOYMENT_RELEASE_CHANNEL_EVIDENCE_INDEX_SCHEMA,
        "status": status,
        "created_at": "2026-06-15T04:15:00Z",
        "index_name": "local-release-channel-evidence-index",
        "publication_path": "outputs/deployment_release_channel_publication_manifest.json",
        "publication": {
            "path": "outputs/deployment_release_channel_publication_manifest.json",
            "sha256": "0" * 64,
            "readable": True,
            "json_valid": True,
            "schema_version": 1,
            "status": "ready",
            "created_at": "2026-06-15T04:00:00Z",
            "publication_channel": "local-release-channel-publication",
        },
        "package": {
            "package_name": "vyu-local-serverless-entrypoint",
            "runtime": "python3.11",
            "handler": "apps.serverless.handler.handler",
        },
        "operator": {"id": "release-operator", "role": "deployment_operator"},
        "decision": {"value": "approve", "comment": "Release-channel preparation accepted for local handoff."},
        "publication_steps": ["Verify accepted release evidence before transfer."],
        "local_only_limits": ["no_artifact_transfer", "no_ci_upload", "no_signing_or_kms"],
        "evidence_items": evidence_items,
        "summary": {
            "passed": 17 if passed else 16,
            "failed": 0 if passed else 1,
            "total": 17,
            "evidence_item_count": len(evidence_items),
            "required_evidence_item_count": 8,
            "present_required_evidence_item_count": 7 if missing_required_hash else 8,
        },
        "checks": [
            {"name": "publication_status_ready", "passed": status == "ready", "detail": status},
            {"name": "required_evidence_items_present", "passed": not missing_required_hash, "detail": "required=8"},
            {"name": "handoff_archive_hash_bound", "passed": not failed_check, "detail": "handoff_archive"},
        ],
    }
    path = outputs / "deployment_release_channel_evidence_index.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return Path("outputs/deployment_release_channel_evidence_index.json")


def _item(
    name: str,
    role: str,
    sha256: str | None,
    source_field: str,
    *,
    required: bool = True,
    expected_sha256: str | None = None,
    hash_matches_expected: bool | None = None,
) -> dict[str, object]:
    return {
        "name": name,
        "role": role,
        "sha256": sha256,
        "source_field": source_field,
        "required": required,
        "expected_sha256": expected_sha256,
        "hash_matches_expected": hash_matches_expected,
        "present": bool(sha256),
    }


if __name__ == "__main__":
    unittest.main()
