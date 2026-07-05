import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.vyu.deployment import (
    DEPLOYMENT_RELEASE_EVIDENCE_SUMMARY_SCHEMA,
    DEPLOYMENT_RELEASE_REVIEW_SCHEMA,
    DeploymentReleaseReviewDecision,
    build_deployment_release_review_decision,
    write_deployment_release_review_decision,
)


class DeploymentReleaseReviewTests(unittest.TestCase):
    def test_review_approves_ready_summary_and_binds_summary_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path = _write_summary(root, status="ready")
            summary_sha256 = _sha256(summary_path)

            review = build_deployment_release_review_decision(
                summary_path=summary_path,
                decision="approve",
                reviewer_id="deployment-operator",
                reviewer_role="deployment_operator",
                comment="Release evidence reviewed locally.",
                decided_at="2026-06-15T02:45:00Z",
            )

        payload = review.to_json()
        checks = {check["name"]: check for check in payload["checks"]}

        self.assertIsInstance(review, DeploymentReleaseReviewDecision)
        self.assertEqual(DEPLOYMENT_RELEASE_REVIEW_SCHEMA, payload["schema_version"])
        self.assertEqual("approved", payload["status"])
        self.assertEqual("approve", payload["decision"]["value"])
        self.assertEqual(summary_sha256, payload["summary"]["sha256"])
        self.assertEqual("ready", payload["summary"]["status"])
        self.assertEqual("vyu-local-serverless-entrypoint", payload["package"]["package_name"])
        self.assertTrue(payload["command_summary"]["commands_match"])
        self.assertEqual([], payload["blocking_reasons"])
        self.assertTrue(checks["summary_schema_supported"]["passed"])
        self.assertTrue(checks["summary_status_ready"]["passed"])
        self.assertTrue(checks["approve_requires_ready_summary"]["passed"])

    def test_review_blocks_approval_when_summary_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path = _write_summary(root, status="blocked", failed_checks=1)

            review = build_deployment_release_review_decision(
                summary_path=summary_path,
                decision="approve",
                reviewer_id="deployment-operator",
                reviewer_role="deployment_operator",
                comment="Cannot approve until upstream evidence is ready.",
                decided_at="2026-06-15T02:46:00Z",
            )

        payload = review.to_json()
        checks = {check["name"]: check for check in payload["checks"]}

        self.assertEqual("blocked", payload["status"])
        self.assertFalse(checks["summary_status_ready"]["passed"])
        self.assertFalse(checks["approve_requires_ready_summary"]["passed"])
        self.assertIn("summary_status_ready", payload["blocking_reasons"])
        self.assertIn("approve_requires_ready_summary", payload["blocking_reasons"])

    def test_review_records_operator_block_against_ready_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path = _write_summary(root, status="ready")

            review = build_deployment_release_review_decision(
                summary_path=summary_path,
                decision="block",
                reviewer_id="deployment-operator",
                reviewer_role="deployment_operator",
                comment="Holding release for manual environment window.",
                decided_at="2026-06-15T02:47:00Z",
            )

        payload = review.to_json()
        checks = {check["name"]: check for check in payload["checks"]}

        self.assertEqual("blocked", payload["status"])
        self.assertEqual("block", payload["decision"]["value"])
        self.assertTrue(checks["summary_status_ready"]["passed"])
        self.assertTrue(checks["approve_requires_ready_summary"]["passed"])
        self.assertEqual(["operator_decision_block"], payload["blocking_reasons"])

    def test_review_writer_and_command_write_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path = _write_summary(root, status="ready")
            output = root / "deployment_release_review_decision.json"

            review = build_deployment_release_review_decision(
                summary_path=summary_path,
                decision="approve",
                reviewer_id="deployment-operator",
                reviewer_role="deployment_operator",
                comment="Release evidence reviewed locally.",
                decided_at="2026-06-15T02:48:00Z",
            )
            write_deployment_release_review_decision(review, output)
            written_payload = json.loads(output.read_text(encoding="utf-8"))

            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/review_deployment_release_evidence.py",
                    "--summary",
                    str(summary_path),
                    "--decision",
                    "approve",
                    "--reviewer-id",
                    "deployment-operator",
                    "--reviewer-role",
                    "deployment_operator",
                    "--comment",
                    "Release evidence reviewed locally.",
                    "--decided-at",
                    "2026-06-15T02:49:00Z",
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

        self.assertEqual("approved", written_payload["status"])
        self.assertEqual(proc.stderr, "")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertEqual("approved", command_payload["status"])
        self.assertEqual(command_payload, file_payload)
        self.assertEqual("2026-06-15T02:49:00Z", file_payload["decided_at"])


PACKAGE = {
    "package_name": "vyu-local-serverless-entrypoint",
    "deployment_target": "serverless-http",
    "runtime": "python3.11",
    "handler": "apps.serverless.handler.handler",
}


def _write_summary(root: Path, *, status: str, failed_checks: int = 0) -> Path:
    path = root / "deployment_release_evidence_summary.json"
    passed = 14 - failed_checks
    payload = {
        "schema_version": DEPLOYMENT_RELEASE_EVIDENCE_SUMMARY_SCHEMA,
        "status": status,
        "created_at": "2026-06-15T02:30:00Z",
        "package_evidence_path": "outputs/deployment_package_evidence.json",
        "release_checklist_path": "outputs/deployment_release_package_checklist.json",
        "transcript_bundle_path": "outputs/deployment_transcript_bundle.json",
        "inputs": {},
        "package": PACKAGE,
        "artifact_hashes": {
            "package_evidence_sha256": "a" * 64,
            "release_checklist_sha256": "b" * 64,
            "transcript_bundle_sha256": "c" * 64,
            "archive_sha256": "d" * 64,
            "inventory_sha256": "e" * 64,
            "checklist_evidence_sha256": "a" * 64,
        },
        "command_summary": {
            "required_command_count": 7,
            "bundle_required_command_count": 7,
            "covered_command_count": 7,
            "commands_match": True,
        },
        "summary": {"passed": passed, "failed": failed_checks, "total": 14},
        "checks": [
            {"name": "summary_fixture", "passed": failed_checks == 0, "detail": "fixture"},
        ],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
