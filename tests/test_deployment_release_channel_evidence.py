import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.vyu.deployment import (
    DEPLOYMENT_RELEASE_CHANNEL_EVIDENCE_INDEX_SCHEMA,
    DEPLOYMENT_RELEASE_CHANNEL_PUBLICATION_SCHEMA,
    DeploymentReleaseChannelEvidenceIndex,
    build_deployment_release_channel_evidence_index,
    write_deployment_release_channel_evidence_index,
)


class DeploymentReleaseChannelEvidenceIndexTests(unittest.TestCase):
    def test_evidence_index_is_ready_for_ready_publication_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            publication_path = _write_publication_fixture(root)

            index = build_deployment_release_channel_evidence_index(
                publication_path=publication_path,
                root=root,
                index_name="local-release-channel-evidence-index",
                created_at="2026-06-15T04:15:00Z",
            )

        payload = index.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        evidence = {item["name"]: item for item in payload["evidence_items"]}

        self.assertIsInstance(index, DeploymentReleaseChannelEvidenceIndex)
        self.assertEqual(DEPLOYMENT_RELEASE_CHANNEL_EVIDENCE_INDEX_SCHEMA, payload["schema_version"])
        self.assertEqual("ready", payload["status"])
        self.assertEqual("local-release-channel-evidence-index", payload["index_name"])
        self.assertRegex(payload["publication"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual("ready", payload["publication"]["status"])
        self.assertEqual("vyu-local-serverless-entrypoint", payload["package"]["package_name"])
        self.assertEqual("release-operator", payload["operator"]["id"])
        self.assertEqual("approve", payload["decision"]["value"])
        self.assertEqual("1" * 64, evidence["acceptance_record"]["sha256"])
        self.assertEqual("2" * 64, evidence["preparation_manifest"]["sha256"])
        self.assertEqual("3" * 64, evidence["handoff_inventory"]["sha256"])
        self.assertEqual("4" * 64, evidence["handoff_archive"]["sha256"])
        self.assertEqual("4" * 64, evidence["handoff_archive"]["expected_sha256"])
        self.assertTrue(evidence["handoff_archive"]["hash_matches_expected"])
        self.assertEqual("5" * 64, evidence["release_evidence_summary"]["sha256"])
        self.assertEqual("6" * 64, evidence["release_review_decision"]["sha256"])
        self.assertEqual("7" * 64, evidence["package_evidence"]["sha256"])
        self.assertTrue(checks["publication_status_ready"]["passed"])
        self.assertTrue(checks["publication_checks_passed"]["passed"])
        self.assertTrue(checks["acceptance_sha256_present"]["passed"])
        self.assertTrue(checks["handoff_archive_hash_bound"]["passed"])
        self.assertTrue(checks["required_evidence_items_present"]["passed"])
        self.assertEqual(payload["summary"]["required_evidence_item_count"], payload["summary"]["present_required_evidence_item_count"])

    def test_evidence_index_blocks_when_publication_is_blocked_or_has_failed_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            publication_path = _write_publication_fixture(root, status="blocked", failed_check=True)

            index = build_deployment_release_channel_evidence_index(
                publication_path=publication_path,
                root=root,
                created_at="2026-06-15T04:16:00Z",
            )

        payload = index.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("blocked", payload["status"])
        self.assertFalse(checks["publication_status_ready"]["passed"])
        self.assertFalse(checks["publication_checks_passed"]["passed"])

    def test_evidence_index_blocks_when_required_hashes_are_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            publication_path = _write_publication_fixture(root, missing_required_hash=True)

            index = build_deployment_release_channel_evidence_index(
                publication_path=publication_path,
                root=root,
                created_at="2026-06-15T04:17:00Z",
            )

        payload = index.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("blocked", payload["status"])
        self.assertFalse(checks["preparation_inventory_sha256_present"]["passed"])
        self.assertFalse(checks["required_evidence_items_present"]["passed"])

    def test_writer_and_command_write_evidence_index_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            publication_path = _write_publication_fixture(root)
            output_path = root / "outputs" / "deployment_release_channel_evidence_index.json"

            index = build_deployment_release_channel_evidence_index(
                publication_path=publication_path,
                root=root,
                created_at="2026-06-15T04:18:00Z",
            )
            write_deployment_release_channel_evidence_index(index, output_path)
            written_payload = json.loads(output_path.read_text(encoding="utf-8"))

            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/build_deployment_release_channel_evidence.py",
                    "--publication",
                    "outputs/deployment_release_channel_publication_manifest.json",
                    "--root",
                    str(root),
                    "--index-name",
                    "local-release-channel-evidence-index",
                    "--created-at",
                    "2026-06-15T04:19:00Z",
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
        self.assertEqual("2026-06-15T04:19:00Z", file_payload["created_at"])
        self.assertEqual("local-release-channel-evidence-index", file_payload["index_name"])


def _write_publication_fixture(
    root: Path,
    *,
    status: str = "ready",
    failed_check: bool = False,
    missing_required_hash: bool = False,
) -> Path:
    outputs = root / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    checks = [
        {"name": "acceptance_status_accepted", "passed": status == "ready", "detail": "accepted" if status == "ready" else "blocked"},
        {"name": "acceptance_decision_approves", "passed": not failed_check, "detail": "approve" if not failed_check else "block"},
        {"name": "preparation_archive_hash_bound", "passed": not failed_check, "detail": "archive"},
        {"name": "local_only_limits_recorded", "passed": True, "detail": "count=8"},
    ]
    payload = {
        "schema_version": DEPLOYMENT_RELEASE_CHANNEL_PUBLICATION_SCHEMA,
        "status": status,
        "created_at": "2026-06-15T04:00:00Z",
        "publication_channel": "local-release-channel-publication",
        "acceptance_path": "outputs/deployment_release_channel_acceptance.json",
        "acceptance": {
            "path": "outputs/deployment_release_channel_acceptance.json",
            "sha256": "1" * 64,
            "readable": True,
            "json_valid": True,
            "schema_version": 1,
            "status": "accepted",
            "decided_at": "2026-06-15T03:45:00Z",
        },
        "package": {
            "package_name": "vyu-local-serverless-entrypoint",
            "runtime": "python3.11",
            "handler": "apps.serverless.handler.handler",
        },
        "preparation": {
            "path": "outputs/deployment_release_channel_preparation.json",
            "sha256": "2" * 64,
            "status": "ready",
            "channel": "local-release-channel",
        },
        "preparation_artifact_hashes": {
            "handoff_inventory_sha256": "3" * 64,
            "handoff_archive_sha256": "4" * 64,
            "release_evidence_summary_sha256": "5" * 64,
            "release_review_decision_sha256": "6" * 64,
            "package_evidence_sha256": "7" * 64,
            "release_checklist_sha256": "8" * 64,
            "transcript_bundle_sha256": "9" * 64,
        },
        "preparation_archive": {
            "requested": True,
            "path": "outputs/deployment_release_handoff.zip",
            "sha256": "4" * 64,
            "expected_sha256": "4" * 64,
            "hash_matches_expected": True,
        },
        "preparation_inventory_sha256": None if missing_required_hash else "3" * 64,
        "operator": {
            "id": "release-operator",
            "role": "deployment_operator",
        },
        "decision": {
            "value": "approve",
            "comment": "Release-channel preparation accepted for local handoff.",
        },
        "publication_steps": ["Verify accepted release evidence before transfer."],
        "local_only_limits": ["no_artifact_transfer", "no_ci_upload", "no_signing_or_kms"],
        "summary": {
            "passed": 14 if status == "ready" and not failed_check and not missing_required_hash else 13,
            "failed": 0 if status == "ready" and not failed_check and not missing_required_hash else 1,
            "total": 14,
        },
        "checks": checks,
    }
    path = outputs / "deployment_release_channel_publication_manifest.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return Path("outputs/deployment_release_channel_publication_manifest.json")


if __name__ == "__main__":
    unittest.main()
