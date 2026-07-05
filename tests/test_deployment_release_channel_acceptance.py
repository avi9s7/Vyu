import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.vyu.deployment import (
    DEPLOYMENT_RELEASE_CHANNEL_ACCEPTANCE_SCHEMA,
    DEPLOYMENT_RELEASE_CHANNEL_PREPARATION_SCHEMA,
    DeploymentReleaseChannelAcceptanceRecord,
    build_deployment_release_channel_acceptance_record,
    write_deployment_release_channel_acceptance_record,
)


class DeploymentReleaseChannelAcceptanceTests(unittest.TestCase):
    def test_acceptance_marks_accepted_when_preparation_is_ready_and_operator_approves(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            preparation_path = _write_preparation_fixture(root)

            record = build_deployment_release_channel_acceptance_record(
                preparation_path=preparation_path,
                decision="approve",
                operator_id="release-operator",
                operator_role="deployment_operator",
                comment="Release-channel preparation accepted for local handoff.",
                decided_at="2026-06-15T03:45:00Z",
                root=root,
            )

        payload = record.to_json()
        checks = {check["name"]: check for check in payload["checks"]}

        self.assertIsInstance(record, DeploymentReleaseChannelAcceptanceRecord)
        self.assertEqual(DEPLOYMENT_RELEASE_CHANNEL_ACCEPTANCE_SCHEMA, payload["schema_version"])
        self.assertEqual("accepted", payload["status"])
        self.assertIn("deployment-release-channel-acceptance", payload["acceptance_id"])
        self.assertEqual("release-operator", payload["operator"]["id"])
        self.assertEqual("deployment_operator", payload["operator"]["role"])
        self.assertEqual("approve", payload["decision"]["value"])
        self.assertRegex(payload["preparation"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual("local-release-channel", payload["preparation"]["channel"])
        self.assertEqual("vyu-local-serverless-entrypoint", payload["package"]["package_name"])
        self.assertEqual("1" * 64, payload["preparation_inventory_sha256"])
        self.assertEqual("2" * 64, payload["preparation_archive"]["sha256"])
        self.assertEqual("2" * 64, payload["preparation_archive"]["expected_sha256"])
        self.assertEqual("3" * 64, payload["preparation_artifact_hashes"]["handoff_inventory_sha256"])
        self.assertEqual(["Verify hashes before transfer."], payload["next_actions"])
        self.assertEqual([], payload["blocking_reasons"])
        self.assertTrue(checks["preparation_status_ready"]["passed"])
        self.assertTrue(checks["preparation_checks_passed"]["passed"])
        self.assertTrue(checks["preparation_inventory_sha256_present"]["passed"])
        self.assertTrue(checks["preparation_archive_hash_bound"]["passed"])
        self.assertTrue(checks["approve_requires_ready_preparation"]["passed"])

    def test_acceptance_blocks_when_preparation_is_blocked_or_has_failed_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            preparation_path = _write_preparation_fixture(root, status="blocked", failed_check=True)

            record = build_deployment_release_channel_acceptance_record(
                preparation_path=preparation_path,
                decision="approve",
                operator_id="release-operator",
                operator_role="deployment_operator",
                comment="Attempted approval should remain blocked.",
                decided_at="2026-06-15T03:46:00Z",
                root=root,
            )

        payload = record.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("blocked", payload["status"])
        self.assertIn("preparation_status_ready", payload["blocking_reasons"])
        self.assertIn("preparation_checks_passed", payload["blocking_reasons"])
        self.assertFalse(checks["preparation_status_ready"]["passed"])
        self.assertFalse(checks["preparation_checks_passed"]["passed"])
        self.assertFalse(checks["approve_requires_ready_preparation"]["passed"])

    def test_acceptance_blocks_when_required_archive_hash_binding_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            preparation_path = _write_preparation_fixture(root, archive_hash_bound=False)

            record = build_deployment_release_channel_acceptance_record(
                preparation_path=preparation_path,
                decision="approve",
                operator_id="release-operator",
                operator_role="deployment_operator",
                comment="Archive hash binding is required before acceptance.",
                decided_at="2026-06-15T03:47:00Z",
                root=root,
            )

        payload = record.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("blocked", payload["status"])
        self.assertIn("preparation_archive_hash_bound", payload["blocking_reasons"])
        self.assertFalse(checks["preparation_archive_hash_bound"]["passed"])

    def test_operator_block_decision_and_command_write_acceptance_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            preparation_path = _write_preparation_fixture(root)
            output_path = root / "outputs" / "deployment_release_channel_acceptance.json"

            record = build_deployment_release_channel_acceptance_record(
                preparation_path=preparation_path,
                decision="block",
                operator_id="release-operator",
                operator_role="deployment_operator",
                comment="Operator held the release-channel handoff for review.",
                decided_at="2026-06-15T03:48:00Z",
                root=root,
            )
            write_deployment_release_channel_acceptance_record(record, output_path)
            written_payload = json.loads(output_path.read_text(encoding="utf-8"))

            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/accept_deployment_release_channel.py",
                    "--preparation",
                    "outputs/deployment_release_channel_preparation.json",
                    "--root",
                    str(root),
                    "--decision",
                    "approve",
                    "--operator-id",
                    "release-operator",
                    "--operator-role",
                    "deployment_operator",
                    "--comment",
                    "Release-channel preparation accepted for local handoff.",
                    "--decided-at",
                    "2026-06-15T03:49:00Z",
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

        self.assertEqual("blocked", written_payload["status"])
        self.assertIn("operator_decision_block", written_payload["blocking_reasons"])
        self.assertEqual(proc.stderr, "")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertEqual("accepted", command_payload["status"])
        self.assertEqual(command_payload, file_payload)
        self.assertEqual("2026-06-15T03:49:00Z", file_payload["decided_at"])


def _write_preparation_fixture(
    root: Path,
    *,
    status: str = "ready",
    failed_check: bool = False,
    archive_hash_bound: bool = True,
) -> Path:
    outputs = root / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    checks = [
        {"name": "inventory_status_ready", "passed": status == "ready", "detail": status},
        {"name": "inventory_checks_passed", "passed": not failed_check, "detail": "checks=5" if not failed_check else "failed=recorded_hashes_match_files"},
        {"name": "inventory_artifact_hashes_match", "passed": True, "detail": "artifacts=4"},
        {"name": "archive_hash_matches_inventory", "passed": archive_hash_bound, "detail": "archive"},
        {"name": "next_actions_recorded", "passed": True, "detail": "count=1"},
    ]
    payload = {
        "schema_version": DEPLOYMENT_RELEASE_CHANNEL_PREPARATION_SCHEMA,
        "status": status,
        "created_at": "2026-06-15T03:30:00Z",
        "channel": "local-release-channel",
        "inventory_path": "outputs/deployment_release_handoff_inventory.json",
        "inventory_sha256": "1" * 64,
        "archive": {
            "requested": True,
            "path": "outputs/deployment_release_handoff.zip",
            "sha256": "2" * 64 if archive_hash_bound else None,
            "expected_sha256": "2" * 64,
            "hash_matches_expected": archive_hash_bound,
        },
        "package": {
            "package_name": "vyu-local-serverless-entrypoint",
            "runtime": "python3.11",
            "handler": "apps.serverless.handler.handler",
        },
        "inventory_summary": {
            "included_artifact_count": 4,
            "included_total_bytes": 4096,
        },
        "artifact_hashes": {
            "handoff_inventory_sha256": "3" * 64,
            "handoff_archive_sha256": "2" * 64,
            "release_evidence_summary_sha256": "4" * 64,
            "release_review_decision_sha256": "5" * 64,
            "package_evidence_sha256": "6" * 64,
        },
        "next_actions": ["Verify hashes before transfer."],
        "summary": {
            "passed": 5 if status == "ready" and not failed_check and archive_hash_bound else 4,
            "failed": 0 if status == "ready" and not failed_check and archive_hash_bound else 1,
            "total": 5,
        },
        "checks": checks,
    }
    path = outputs / "deployment_release_channel_preparation.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return Path("outputs/deployment_release_channel_preparation.json")


if __name__ == "__main__":
    unittest.main()
