import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.vyu.deployment import (
    DEPLOYMENT_RELEASE_CHANNEL_ACCEPTANCE_SCHEMA,
    DEPLOYMENT_RELEASE_CHANNEL_PUBLICATION_SCHEMA,
    DeploymentReleaseChannelPublicationManifest,
    build_deployment_release_channel_publication_manifest,
    write_deployment_release_channel_publication_manifest,
)


class DeploymentReleaseChannelPublicationTests(unittest.TestCase):
    def test_publication_manifest_is_ready_for_accepted_hash_bound_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            acceptance_path = _write_acceptance_fixture(root)

            manifest = build_deployment_release_channel_publication_manifest(
                acceptance_path=acceptance_path,
                root=root,
                publication_channel="local-release-channel-publication",
                created_at="2026-06-15T04:00:00Z",
            )

        payload = manifest.to_json()
        checks = {check["name"]: check for check in payload["checks"]}

        self.assertIsInstance(manifest, DeploymentReleaseChannelPublicationManifest)
        self.assertEqual(DEPLOYMENT_RELEASE_CHANNEL_PUBLICATION_SCHEMA, payload["schema_version"])
        self.assertEqual("ready", payload["status"])
        self.assertEqual("local-release-channel-publication", payload["publication_channel"])
        self.assertRegex(payload["acceptance"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual("accepted", payload["acceptance"]["status"])
        self.assertEqual("vyu-local-serverless-entrypoint", payload["package"]["package_name"])
        self.assertEqual("ready", payload["preparation"]["status"])
        self.assertEqual("1" * 64, payload["preparation"]["sha256"])
        self.assertEqual("2" * 64, payload["preparation_inventory_sha256"])
        self.assertEqual("3" * 64, payload["preparation_archive"]["sha256"])
        self.assertEqual("3" * 64, payload["preparation_archive"]["expected_sha256"])
        self.assertEqual("4" * 64, payload["preparation_artifact_hashes"]["handoff_inventory_sha256"])
        self.assertEqual("release-operator", payload["operator"]["id"])
        self.assertEqual("approve", payload["decision"]["value"])
        self.assertGreaterEqual(len(payload["publication_steps"]), 3)
        self.assertIn("no_artifact_transfer", payload["local_only_limits"])
        self.assertTrue(checks["acceptance_status_accepted"]["passed"])
        self.assertTrue(checks["acceptance_decision_approves"]["passed"])
        self.assertTrue(checks["preparation_hash_present"]["passed"])
        self.assertTrue(checks["preparation_archive_hash_bound"]["passed"])
        self.assertTrue(checks["publication_steps_recorded"]["passed"])

    def test_publication_manifest_blocks_when_acceptance_is_blocked_or_has_reasons(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            acceptance_path = _write_acceptance_fixture(root, status="blocked", decision="block", blocking_reasons=["operator_decision_block"])

            manifest = build_deployment_release_channel_publication_manifest(
                acceptance_path=acceptance_path,
                root=root,
                created_at="2026-06-15T04:01:00Z",
            )

        payload = manifest.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("blocked", payload["status"])
        self.assertFalse(checks["acceptance_status_accepted"]["passed"])
        self.assertFalse(checks["acceptance_decision_approves"]["passed"])
        self.assertFalse(checks["acceptance_blocking_reasons_absent"]["passed"])

    def test_publication_manifest_blocks_when_archive_binding_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            acceptance_path = _write_acceptance_fixture(root, archive_hash_bound=False)

            manifest = build_deployment_release_channel_publication_manifest(
                acceptance_path=acceptance_path,
                root=root,
                created_at="2026-06-15T04:02:00Z",
            )

        payload = manifest.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("blocked", payload["status"])
        self.assertFalse(checks["preparation_archive_hash_bound"]["passed"])

    def test_writer_and_command_write_publication_manifest_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            acceptance_path = _write_acceptance_fixture(root)
            output_path = root / "outputs" / "deployment_release_channel_publication_manifest.json"

            manifest = build_deployment_release_channel_publication_manifest(
                acceptance_path=acceptance_path,
                root=root,
                created_at="2026-06-15T04:03:00Z",
            )
            write_deployment_release_channel_publication_manifest(manifest, output_path)
            written_payload = json.loads(output_path.read_text(encoding="utf-8"))

            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/prepare_deployment_release_channel_publication.py",
                    "--acceptance",
                    "outputs/deployment_release_channel_acceptance.json",
                    "--root",
                    str(root),
                    "--publication-channel",
                    "local-release-channel-publication",
                    "--created-at",
                    "2026-06-15T04:04:00Z",
                    "--publication-step",
                    "Verify accepted release evidence before transfer.",
                    "--local-only-limit",
                    "no_artifact_transfer",
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
        self.assertEqual(["Verify accepted release evidence before transfer."], file_payload["publication_steps"])
        self.assertEqual(["no_artifact_transfer"], file_payload["local_only_limits"])
        self.assertEqual("2026-06-15T04:04:00Z", file_payload["created_at"])


def _write_acceptance_fixture(
    root: Path,
    *,
    status: str = "accepted",
    decision: str = "approve",
    blocking_reasons: list[str] | None = None,
    archive_hash_bound: bool = True,
) -> Path:
    outputs = root / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": DEPLOYMENT_RELEASE_CHANNEL_ACCEPTANCE_SCHEMA,
        "status": status,
        "acceptance_id": "deployment-release-channel-acceptance-abc123-release-operator-deployment_operator",
        "decided_at": "2026-06-15T03:45:00Z",
        "preparation_path": "outputs/deployment_release_channel_preparation.json",
        "preparation": {
            "path": "outputs/deployment_release_channel_preparation.json",
            "sha256": "1" * 64,
            "readable": True,
            "json_valid": True,
            "schema_version": 1,
            "status": "ready",
            "created_at": "2026-06-15T03:30:00Z",
            "channel": "local-release-channel",
        },
        "package": {
            "package_name": "vyu-local-serverless-entrypoint",
            "runtime": "python3.11",
            "handler": "apps.serverless.handler.handler",
        },
        "preparation_artifact_hashes": {
            "handoff_inventory_sha256": "4" * 64,
            "handoff_archive_sha256": "3" * 64,
            "release_evidence_summary_sha256": "5" * 64,
            "release_review_decision_sha256": "6" * 64,
        },
        "preparation_archive": {
            "requested": True,
            "path": "outputs/deployment_release_handoff.zip",
            "sha256": "3" * 64 if archive_hash_bound else None,
            "expected_sha256": "3" * 64,
            "hash_matches_expected": archive_hash_bound,
        },
        "preparation_inventory_sha256": "2" * 64,
        "next_actions": ["Verify hashes before transfer."],
        "operator": {
            "id": "release-operator",
            "role": "deployment_operator",
        },
        "decision": {
            "value": decision,
            "comment": "Release-channel preparation accepted for local handoff.",
        },
        "blocking_reasons": blocking_reasons or [],
        "acceptance_summary": {
            "passed": 12 if status == "accepted" and decision == "approve" and not blocking_reasons and archive_hash_bound else 11,
            "failed": 0 if status == "accepted" and decision == "approve" and not blocking_reasons and archive_hash_bound else 1,
            "total": 12,
        },
        "checks": [
            {"name": "preparation_status_ready", "passed": True, "detail": "ready"},
            {"name": "preparation_checks_passed", "passed": True, "detail": "checks=12"},
            {"name": "preparation_archive_hash_bound", "passed": archive_hash_bound, "detail": "archive"},
            {"name": "approve_requires_ready_preparation", "passed": decision == "approve" and status == "accepted", "detail": "decision=approve,preparation_status=ready"},
        ],
    }
    path = outputs / "deployment_release_channel_acceptance.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return Path("outputs/deployment_release_channel_acceptance.json")


if __name__ == "__main__":
    unittest.main()
