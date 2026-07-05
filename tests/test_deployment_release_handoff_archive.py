import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import zipfile

from src.vyu.deployment import (
    DEPLOYMENT_RELEASE_EVIDENCE_SUMMARY_SCHEMA,
    DEPLOYMENT_RELEASE_HANDOFF_ARCHIVE_SCHEMA,
    DEPLOYMENT_RELEASE_HANDOFF_SCHEMA,
    DEPLOYMENT_RELEASE_REVIEW_SCHEMA,
    DeploymentReleaseHandoffArchiveInventory,
    build_deployment_release_handoff_archive_inventory,
)


class DeploymentReleaseHandoffArchiveTests(unittest.TestCase):
    def test_inventory_and_archive_are_ready_and_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff_path = _write_handoff_fixture(root)
            first_archive = root / "outputs" / "handoff-first.zip"
            second_archive = root / "outputs" / "handoff-second.zip"

            first = build_deployment_release_handoff_archive_inventory(
                handoff_path=handoff_path,
                root=root,
                archive_path=first_archive,
                created_at="2026-06-15T03:15:00Z",
            )
            second = build_deployment_release_handoff_archive_inventory(
                handoff_path=handoff_path,
                root=root,
                archive_path=second_archive,
                created_at="2026-06-15T03:15:00Z",
            )
            with zipfile.ZipFile(first_archive, "r") as archive:
                names = archive.namelist()

        payload = first.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        artifact_names = {artifact["name"] for artifact in payload["artifacts"]}

        self.assertIsInstance(first, DeploymentReleaseHandoffArchiveInventory)
        self.assertEqual(DEPLOYMENT_RELEASE_HANDOFF_ARCHIVE_SCHEMA, payload["schema_version"])
        self.assertEqual("ready", payload["status"])
        self.assertEqual("2026-06-15T03:15:00Z", payload["created_at"])
        self.assertEqual(first.archive_sha256, second.archive_sha256)
        self.assertEqual(6, payload["summary"]["included_artifact_count"])
        self.assertEqual("vyu-local-serverless-entrypoint", payload["package"]["package_name"])
        self.assertIn("outputs/deployment_release_handoff.json", names)
        self.assertIn("outputs/deployment_release_evidence_summary.json", names)
        self.assertIn("outputs/deployment_release_review_decision.json", names)
        self.assertIn("outputs/deployment_package_evidence.json", names)
        self.assertIn("outputs/deployment_release_package_checklist.json", names)
        self.assertIn("outputs/deployment_transcript_bundle.json", names)
        self.assertEqual(
            {
                "deployment_release_handoff",
                "release_evidence_summary",
                "release_review_decision",
                "deployment_package_evidence",
                "deployment_release_package_checklist",
                "deployment_transcript_bundle",
            },
            artifact_names,
        )
        self.assertTrue(checks["handoff_status_ready"]["passed"])
        self.assertTrue(checks["recorded_hashes_match_files"]["passed"])
        self.assertTrue(checks["archive_entries_match_inventory"]["passed"])
        self.assertTrue(checks["archive_entry_hashes_match_inventory"]["passed"])
        self.assertTrue(checks["archive_metadata_deterministic"]["passed"])
        self.assertRegex(payload["archive"]["sha256"], r"^[0-9a-f]{64}$")

    def test_inventory_blocks_when_handoff_is_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff_path = _write_handoff_fixture(root, handoff_status="blocked")
            archive_path = root / "outputs" / "handoff.zip"

            inventory = build_deployment_release_handoff_archive_inventory(
                handoff_path=handoff_path,
                root=root,
                archive_path=archive_path,
                created_at="2026-06-15T03:16:00Z",
            )

        payload = inventory.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("blocked", payload["status"])
        self.assertFalse(checks["handoff_status_ready"]["passed"])
        self.assertFalse(checks["handoff_archive_written"]["passed"])
        self.assertIsNone(payload["archive"]["sha256"])

    def test_inventory_blocks_when_referenced_evidence_hash_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff_path = _write_handoff_fixture(root)
            package_evidence = root / "outputs" / "deployment_package_evidence.json"
            payload = json.loads(package_evidence.read_text(encoding="utf-8"))
            payload["status"] = "tampered"
            _write_json(package_evidence, payload)

            inventory = build_deployment_release_handoff_archive_inventory(
                handoff_path=handoff_path,
                root=root,
                created_at="2026-06-15T03:17:00Z",
            )

        payload = inventory.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        artifacts = {artifact["name"]: artifact for artifact in payload["artifacts"]}
        self.assertEqual("blocked", payload["status"])
        self.assertFalse(checks["recorded_hashes_match_files"]["passed"])
        self.assertFalse(artifacts["deployment_package_evidence"]["hash_matches_expected"])

    def test_command_writes_inventory_and_archive_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_handoff_fixture(root)
            inventory_path = root / "outputs" / "deployment_release_handoff_inventory.json"
            archive_path = root / "outputs" / "deployment_release_handoff.zip"
            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/build_deployment_release_handoff_archive.py",
                    "--handoff",
                    "outputs/deployment_release_handoff.json",
                    "--root",
                    str(root),
                    "--created-at",
                    "2026-06-15T03:18:00Z",
                    "--inventory",
                    str(inventory_path),
                    "--archive",
                    str(archive_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
                check=False,
            )
            stdout_payload = json.loads(proc.stdout)
            file_payload = json.loads(inventory_path.read_text(encoding="utf-8"))
            archive_exists = archive_path.exists()

        self.assertEqual(proc.stderr, "")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertTrue(archive_exists)
        self.assertEqual("ready", stdout_payload["status"])
        self.assertEqual(stdout_payload, file_payload)
        self.assertEqual("2026-06-15T03:18:00Z", file_payload["created_at"])
        self.assertRegex(file_payload["archive"]["sha256"], r"^[0-9a-f]{64}$")


def _write_handoff_fixture(root: Path, *, handoff_status: str = "ready") -> Path:
    outputs = root / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)

    package_evidence_path = outputs / "deployment_package_evidence.json"
    release_checklist_path = outputs / "deployment_release_package_checklist.json"
    transcript_bundle_path = outputs / "deployment_transcript_bundle.json"
    summary_path = outputs / "deployment_release_evidence_summary.json"
    review_path = outputs / "deployment_release_review_decision.json"
    handoff_path = outputs / "deployment_release_handoff.json"

    _write_json(
        package_evidence_path,
        {
            "schema_version": 1,
            "status": "complete",
            "manifest_path": "deploy/serverless/package.manifest.json",
            "archive_path": "outputs/vyu_deployment_package.zip",
            "inventory_path": "outputs/deployment_package_inventory.json",
            "artifact_hashes": {"archive_sha256": "d" * 64, "inventory_sha256": "e" * 64},
        },
    )
    _write_json(
        release_checklist_path,
        {
            "schema_version": 1,
            "status": "ready",
            "evidence_path": "outputs/deployment_package_evidence.json",
            "artifact_hashes": {"evidence_sha256": _sha256(package_evidence_path)},
        },
    )
    _write_json(
        transcript_bundle_path,
        {
            "schema_version": 1,
            "status": "ready",
            "summary": {"covered_command_count": 7},
        },
    )

    artifact_hashes = {
        "package_evidence_sha256": _sha256(package_evidence_path),
        "release_checklist_sha256": _sha256(release_checklist_path),
        "transcript_bundle_sha256": _sha256(transcript_bundle_path),
        "archive_sha256": "d" * 64,
        "inventory_sha256": "e" * 64,
        "checklist_evidence_sha256": _sha256(package_evidence_path),
    }
    package = {
        "package_name": "vyu-local-serverless-entrypoint",
        "deployment_target": "serverless-http",
        "runtime": "python3.11",
        "handler": "apps.serverless.handler.handler",
    }
    command_summary = {
        "required_command_count": 7,
        "bundle_required_command_count": 7,
        "covered_command_count": 7,
        "commands_match": True,
    }
    _write_json(
        summary_path,
        {
            "schema_version": DEPLOYMENT_RELEASE_EVIDENCE_SUMMARY_SCHEMA,
            "status": "ready",
            "created_at": "2026-06-15T02:30:00Z",
            "package_evidence_path": "outputs/deployment_package_evidence.json",
            "release_checklist_path": "outputs/deployment_release_package_checklist.json",
            "transcript_bundle_path": "outputs/deployment_transcript_bundle.json",
            "package": package,
            "artifact_hashes": artifact_hashes,
            "command_summary": command_summary,
            "summary": {"passed": 13, "failed": 0, "total": 13},
            "checks": [],
        },
    )
    _write_json(
        review_path,
        {
            "schema_version": DEPLOYMENT_RELEASE_REVIEW_SCHEMA,
            "status": "approved",
            "decision_id": "deployment-release-review-test",
            "decided_at": "2026-06-15T02:45:00Z",
            "summary_path": "outputs/deployment_release_evidence_summary.json",
            "summary": {
                "path": "outputs/deployment_release_evidence_summary.json",
                "sha256": _sha256(summary_path),
                "schema_version": DEPLOYMENT_RELEASE_EVIDENCE_SUMMARY_SCHEMA,
                "status": "ready",
            },
            "package": package,
            "summary_artifact_hashes": artifact_hashes,
            "command_summary": command_summary,
            "reviewer": {"id": "deployment-operator", "role": "deployment_operator"},
            "decision": {"value": "approve", "comment": "Release evidence reviewed locally."},
            "blocking_reasons": [],
        },
    )
    _write_json(
        handoff_path,
        {
            "schema_version": DEPLOYMENT_RELEASE_HANDOFF_SCHEMA,
            "status": handoff_status,
            "created_at": "2026-06-15T03:00:00Z",
            "summary_path": "outputs/deployment_release_evidence_summary.json",
            "review_path": "outputs/deployment_release_review_decision.json",
            "inputs": {
                "release_evidence_summary": {
                    "name": "release_evidence_summary",
                    "path": "outputs/deployment_release_evidence_summary.json",
                    "sha256": _sha256(summary_path),
                    "readable": True,
                    "json_valid": True,
                    "schema_version": DEPLOYMENT_RELEASE_EVIDENCE_SUMMARY_SCHEMA,
                    "status": "ready",
                },
                "release_review_decision": {
                    "name": "release_review_decision",
                    "path": "outputs/deployment_release_review_decision.json",
                    "sha256": _sha256(review_path),
                    "readable": True,
                    "json_valid": True,
                    "schema_version": DEPLOYMENT_RELEASE_REVIEW_SCHEMA,
                    "status": "approved",
                },
            },
            "package": package,
            "artifact_hashes": {
                "release_evidence_summary_sha256": _sha256(summary_path),
                "release_review_decision_sha256": _sha256(review_path),
                **artifact_hashes,
            },
            "command_summary": command_summary,
            "reviewer": {"id": "deployment-operator", "role": "deployment_operator"},
            "decision": {"value": "approve", "comment": "Release evidence reviewed locally."},
            "summary": {"passed": 13 if handoff_status == "ready" else 12, "failed": 0 if handoff_status == "ready" else 1, "total": 13},
            "checks": [],
        },
    )
    return Path("outputs/deployment_release_handoff.json")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
