import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import zipfile

from src.vyu.deployment import (
    DEPLOYMENT_RELEASE_CHANNEL_PREPARATION_SCHEMA,
    DEPLOYMENT_RELEASE_HANDOFF_ARCHIVE_SCHEMA,
    DeploymentReleaseChannelPreparation,
    build_deployment_release_channel_preparation,
    write_deployment_release_channel_preparation,
)


class DeploymentReleaseChannelPreparationTests(unittest.TestCase):
    def test_preparation_marks_ready_when_inventory_and_archive_are_ready_and_hash_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inventory_path, archive_path = _write_inventory_fixture(root)

            preparation = build_deployment_release_channel_preparation(
                inventory_path=inventory_path,
                archive_path=archive_path,
                root=root,
                channel="local-release-channel",
                created_at="2026-06-15T03:30:00Z",
            )

        payload = preparation.to_json()
        checks = {check["name"]: check for check in payload["checks"]}

        self.assertIsInstance(preparation, DeploymentReleaseChannelPreparation)
        self.assertEqual(DEPLOYMENT_RELEASE_CHANNEL_PREPARATION_SCHEMA, payload["schema_version"])
        self.assertEqual("ready", payload["status"])
        self.assertEqual("local-release-channel", payload["channel"])
        self.assertRegex(payload["inventory_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(payload["archive"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(payload["archive"]["hash_matches_expected"])
        self.assertEqual("vyu-local-serverless-entrypoint", payload["package"]["package_name"])
        self.assertEqual(2, payload["inventory_summary"]["included_artifact_count"])
        self.assertIn("handoff_inventory_sha256", payload["artifact_hashes"])
        self.assertIn("handoff_archive_sha256", payload["artifact_hashes"])
        self.assertGreaterEqual(len(payload["next_actions"]), 3)
        self.assertTrue(checks["inventory_status_ready"]["passed"])
        self.assertTrue(checks["inventory_checks_passed"]["passed"])
        self.assertTrue(checks["inventory_artifact_hashes_match"]["passed"])
        self.assertTrue(checks["archive_hash_matches_inventory"]["passed"])
        self.assertTrue(checks["next_actions_recorded"]["passed"])

    def test_preparation_blocks_when_archive_hash_does_not_match_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inventory_path, archive_path = _write_inventory_fixture(root)
            (root / archive_path).write_bytes(b"tampered archive bytes")

            preparation = build_deployment_release_channel_preparation(
                inventory_path=inventory_path,
                archive_path=archive_path,
                root=root,
                created_at="2026-06-15T03:31:00Z",
            )

        payload = preparation.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("blocked", payload["status"])
        self.assertFalse(payload["archive"]["hash_matches_expected"])
        self.assertFalse(checks["archive_hash_matches_inventory"]["passed"])

    def test_preparation_blocks_when_inventory_is_blocked_or_has_failed_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inventory_path, archive_path = _write_inventory_fixture(root, inventory_status="blocked", failed_check=True)

            preparation = build_deployment_release_channel_preparation(
                inventory_path=inventory_path,
                archive_path=archive_path,
                root=root,
                created_at="2026-06-15T03:32:00Z",
            )

        payload = preparation.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("blocked", payload["status"])
        self.assertFalse(checks["inventory_status_ready"]["passed"])
        self.assertFalse(checks["inventory_checks_passed"]["passed"])

    def test_writer_and_command_write_preparation_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inventory_path, archive_path = _write_inventory_fixture(root)
            output_path = root / "outputs" / "deployment_release_channel_preparation.json"

            preparation = build_deployment_release_channel_preparation(
                inventory_path=inventory_path,
                archive_path=archive_path,
                root=root,
                created_at="2026-06-15T03:33:00Z",
            )
            write_deployment_release_channel_preparation(preparation, output_path)
            written_payload = json.loads(output_path.read_text(encoding="utf-8"))

            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/prepare_deployment_release_channel.py",
                    "--inventory",
                    "outputs/deployment_release_handoff_inventory.json",
                    "--archive",
                    "outputs/deployment_release_handoff.zip",
                    "--root",
                    str(root),
                    "--channel",
                    "local-release-channel",
                    "--created-at",
                    "2026-06-15T03:34:00Z",
                    "--next-action",
                    "Verify hashes before release-channel transfer.",
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
        self.assertEqual(["Verify hashes before release-channel transfer."], file_payload["next_actions"])
        self.assertEqual("2026-06-15T03:34:00Z", file_payload["created_at"])


def _write_inventory_fixture(
    root: Path,
    *,
    inventory_status: str = "ready",
    failed_check: bool = False,
) -> tuple[Path, Path]:
    outputs = root / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    archive_path = outputs / "deployment_release_handoff.zip"
    _write_archive(archive_path)
    archive_sha256 = _sha256(archive_path)
    artifacts = [
        {
            "name": "deployment_release_handoff",
            "path": "outputs/deployment_release_handoff.json",
            "archive_entry": "outputs/deployment_release_handoff.json",
            "exists": True,
            "json_valid": True,
            "size_bytes": 120,
            "sha256": "a" * 64,
            "expected_sha256": None,
            "hash_matches_expected": True,
            "include_in_archive": True,
        },
        {
            "name": "release_evidence_summary",
            "path": "outputs/deployment_release_evidence_summary.json",
            "archive_entry": "outputs/deployment_release_evidence_summary.json",
            "exists": True,
            "json_valid": True,
            "size_bytes": 240,
            "sha256": "b" * 64,
            "expected_sha256": "b" * 64,
            "hash_matches_expected": True,
            "include_in_archive": True,
        },
    ]
    checks = [
        {"name": "handoff_status_ready", "passed": inventory_status == "ready", "detail": inventory_status},
        {"name": "recorded_hashes_match_files", "passed": not failed_check, "detail": "complete" if not failed_check else "failed=release_evidence_summary"},
        {"name": "archive_entries_match_inventory", "passed": True, "detail": "entries=2 expected=2"},
        {"name": "archive_entry_hashes_match_inventory", "passed": True, "detail": "entries=2 expected=2"},
        {"name": "archive_metadata_deterministic", "passed": True, "detail": "(2026, 1, 1, 0, 0, 0)"},
    ]
    payload = {
        "schema_version": DEPLOYMENT_RELEASE_HANDOFF_ARCHIVE_SCHEMA,
        "status": inventory_status,
        "created_at": "2026-06-15T03:15:00Z",
        "handoff_path": "outputs/deployment_release_handoff.json",
        "archive": {
            "path": "outputs/deployment_release_handoff.zip",
            "sha256": archive_sha256,
            "requested": True,
            "entry_count": 2,
        },
        "package": {
            "package_name": "vyu-local-serverless-entrypoint",
            "runtime": "python3.11",
            "handler": "apps.serverless.handler.handler",
        },
        "artifact_hashes": {
            "release_evidence_summary_sha256": "b" * 64,
            "release_review_decision_sha256": "c" * 64,
            "package_evidence_sha256": "d" * 64,
        },
        "summary": {
            "artifact_count": 2,
            "included_artifact_count": 2,
            "total_bytes": 360,
            "included_total_bytes": 360,
            "passed": 5 if inventory_status == "ready" and not failed_check else 4,
            "failed": 0 if inventory_status == "ready" and not failed_check else 1,
            "total": 5,
        },
        "artifacts": artifacts,
        "checks": checks,
    }
    inventory_path = outputs / "deployment_release_handoff_inventory.json"
    _write_json(inventory_path, payload)
    return Path("outputs/deployment_release_handoff_inventory.json"), Path("outputs/deployment_release_handoff.zip")


def _write_archive(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("outputs/deployment_release_handoff.json", "{}")
        archive.writestr("outputs/deployment_release_evidence_summary.json", "{}")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
