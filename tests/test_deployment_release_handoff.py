import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.vyu.deployment import (
    DEPLOYMENT_RELEASE_EVIDENCE_SUMMARY_SCHEMA,
    DEPLOYMENT_RELEASE_HANDOFF_SCHEMA,
    DEPLOYMENT_RELEASE_REVIEW_SCHEMA,
    DeploymentReleaseHandoffBundle,
    build_deployment_release_handoff_bundle,
    write_deployment_release_handoff_bundle,
)


class DeploymentReleaseHandoffTests(unittest.TestCase):
    def test_handoff_marks_ready_when_summary_and_review_are_approved_and_hash_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path = _write_summary(root, status="ready")
            review_path = _write_review(root, summary_path=summary_path, status="approved", decision="approve")

            bundle = build_deployment_release_handoff_bundle(
                summary_path=summary_path,
                review_path=review_path,
                created_at="2026-06-15T03:00:00Z",
            )

        payload = bundle.to_json()
        checks = {check["name"]: check for check in payload["checks"]}

        self.assertIsInstance(bundle, DeploymentReleaseHandoffBundle)
        self.assertEqual(DEPLOYMENT_RELEASE_HANDOFF_SCHEMA, payload["schema_version"])
        self.assertEqual("ready", payload["status"])
        self.assertEqual("2026-06-15T03:00:00Z", payload["created_at"])
        self.assertEqual("vyu-local-serverless-entrypoint", payload["package"]["package_name"])
        self.assertRegex(payload["artifact_hashes"]["release_evidence_summary_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(payload["artifact_hashes"]["release_review_decision_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual("deployment-operator", payload["reviewer"]["id"])
        self.assertEqual("approve", payload["decision"]["value"])
        self.assertTrue(payload["command_summary"]["commands_match"])
        self.assertTrue(checks["review_summary_hash_matches_input"]["passed"])
        self.assertTrue(checks["review_status_approved"]["passed"])
        self.assertTrue(checks["review_decision_approves"]["passed"])
        self.assertTrue(checks["review_blocking_reasons_absent"]["passed"])

    def test_handoff_blocks_when_review_points_to_stale_summary_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path = _write_summary(root, status="ready")
            review_path = _write_review(
                root,
                summary_path=summary_path,
                status="approved",
                decision="approve",
                summary_sha256="0" * 64,
            )

            bundle = build_deployment_release_handoff_bundle(
                summary_path=summary_path,
                review_path=review_path,
                created_at="2026-06-15T03:01:00Z",
            )

        payload = bundle.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("blocked", payload["status"])
        self.assertFalse(checks["review_summary_hash_matches_input"]["passed"])
        self.assertTrue(checks["summary_status_ready"]["passed"])
        self.assertTrue(checks["review_status_approved"]["passed"])

    def test_handoff_blocks_when_review_decision_is_operator_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path = _write_summary(root, status="ready")
            review_path = _write_review(
                root,
                summary_path=summary_path,
                status="blocked",
                decision="block",
                blocking_reasons=["operator_decision_block"],
            )

            bundle = build_deployment_release_handoff_bundle(
                summary_path=summary_path,
                review_path=review_path,
                created_at="2026-06-15T03:02:00Z",
            )

        payload = bundle.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("blocked", payload["status"])
        self.assertFalse(checks["review_status_approved"]["passed"])
        self.assertFalse(checks["review_decision_approves"]["passed"])
        self.assertFalse(checks["review_blocking_reasons_absent"]["passed"])

    def test_handoff_writer_and_command_write_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path = _write_summary(root, status="ready")
            review_path = _write_review(root, summary_path=summary_path, status="approved", decision="approve")
            output = root / "deployment_release_handoff.json"

            bundle = build_deployment_release_handoff_bundle(
                summary_path=summary_path,
                review_path=review_path,
                created_at="2026-06-15T03:03:00Z",
            )
            write_deployment_release_handoff_bundle(bundle, output)
            written_payload = json.loads(output.read_text(encoding="utf-8"))

            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/build_deployment_release_handoff.py",
                    "--summary",
                    str(summary_path),
                    "--review",
                    str(review_path),
                    "--created-at",
                    "2026-06-15T03:04:00Z",
                    "--output",
                    str(output),
                ],
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
                check=False,
            )
            command_payload = json.loads(proc.stdout)
            file_payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual("ready", written_payload["status"])
        self.assertEqual(proc.stderr, "")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertEqual("ready", command_payload["status"])
        self.assertEqual(command_payload, file_payload)
        self.assertEqual("2026-06-15T03:04:00Z", file_payload["created_at"])


PACKAGE = {
    "package_name": "vyu-local-serverless-entrypoint",
    "deployment_target": "serverless-http",
    "runtime": "python3.11",
    "handler": "apps.serverless.handler.handler",
}
ARTIFACT_HASHES = {
    "package_evidence_sha256": "a" * 64,
    "release_checklist_sha256": "b" * 64,
    "transcript_bundle_sha256": "c" * 64,
    "archive_sha256": "d" * 64,
    "inventory_sha256": "e" * 64,
    "checklist_evidence_sha256": "a" * 64,
}
COMMAND_SUMMARY = {
    "required_command_count": 7,
    "bundle_required_command_count": 7,
    "covered_command_count": 7,
    "commands_match": True,
}


def _write_summary(root: Path, *, status: str) -> Path:
    path = root / "deployment_release_evidence_summary.json"
    payload = {
        "schema_version": DEPLOYMENT_RELEASE_EVIDENCE_SUMMARY_SCHEMA,
        "status": status,
        "created_at": "2026-06-15T02:30:00Z",
        "package": PACKAGE,
        "artifact_hashes": ARTIFACT_HASHES,
        "command_summary": COMMAND_SUMMARY,
        "summary": {"passed": 14 if status == "ready" else 13, "failed": 0 if status == "ready" else 1, "total": 14},
        "checks": [],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_review(
    root: Path,
    *,
    summary_path: Path,
    status: str,
    decision: str,
    summary_sha256: str | None = None,
    blocking_reasons: list[str] | None = None,
) -> Path:
    path = root / "deployment_release_review_decision.json"
    summary_hash = summary_sha256 or _sha256(summary_path)
    payload = {
        "schema_version": DEPLOYMENT_RELEASE_REVIEW_SCHEMA,
        "status": status,
        "decision_id": "deployment-release-review-test",
        "decided_at": "2026-06-15T02:45:00Z",
        "summary_path": str(summary_path),
        "summary": {
            "path": str(summary_path),
            "sha256": summary_hash,
            "readable": True,
            "json_valid": True,
            "schema_version": DEPLOYMENT_RELEASE_EVIDENCE_SUMMARY_SCHEMA,
            "status": "ready",
            "created_at": "2026-06-15T02:30:00Z",
        },
        "package": PACKAGE,
        "summary_artifact_hashes": ARTIFACT_HASHES,
        "command_summary": COMMAND_SUMMARY,
        "reviewer": {"id": "deployment-operator", "role": "deployment_operator"},
        "decision": {"value": decision, "comment": "Release evidence reviewed locally."},
        "blocking_reasons": blocking_reasons or [],
        "review_summary": {"passed": 7, "failed": 0, "total": 7},
        "checks": [],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
