import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.vyu.deployment import (
    DEPLOYMENT_PACKAGE_EVIDENCE_SCHEMA,
    DeploymentPackageEvidence,
    build_deployment_package_archive,
    build_deployment_package_evidence,
    write_deployment_package_evidence,
)


class DeploymentPackageEvidenceTests(unittest.TestCase):
    def test_evidence_records_archive_hashes_manifest_metadata_and_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "package.zip"
            inventory_path = Path(tmp) / "inventory.json"
            archive = build_deployment_package_archive(
                Path("deploy/serverless/package.manifest.json"),
                root=Path("."),
                archive_path=archive_path,
                inventory_output_path=inventory_path,
            )

            evidence = build_deployment_package_evidence(
                Path("deploy/serverless/package.manifest.json"),
                root=Path("."),
                archive_path=archive_path,
                inventory_path=inventory_path,
                created_at="2026-06-15T00:40:00Z",
            )

        payload = evidence.to_json()
        commands = payload["required_validation_commands"]
        check_map = {check["name"]: check for check in payload["checks"]}

        self.assertIsInstance(evidence, DeploymentPackageEvidence)
        self.assertEqual(DEPLOYMENT_PACKAGE_EVIDENCE_SCHEMA, payload["schema_version"])
        self.assertEqual("complete", payload["status"])
        self.assertEqual("2026-06-15T00:40:00Z", payload["created_at"])
        self.assertEqual("vyu-local-serverless-entrypoint", payload["package"]["package_name"])
        self.assertEqual("python3.11", payload["package"]["runtime"])
        self.assertEqual("apps.serverless.handler.handler", payload["package"]["handler"])
        self.assertEqual(archive.archive_sha256, payload["artifact_hashes"]["archive_sha256"])
        self.assertEqual(archive.inventory_sha256, payload["artifact_hashes"]["inventory_sha256"])
        self.assertEqual("pass", payload["archive_verification"]["status"])
        self.assertTrue(check_map["manifest_validation_passed"]["passed"])
        self.assertTrue(check_map["archive_verification_passed"]["passed"])
        self.assertTrue(check_map["inventory_matches_plan"]["passed"])
        self.assertIn(
            [
                "python",
                "scripts/write_deployment_package_evidence.py",
                "--manifest",
                "deploy/serverless/package.manifest.json",
                "--archive",
                "outputs/vyu_deployment_package.zip",
                "--inventory",
                "outputs/deployment_package_inventory.json",
                "--output",
                "outputs/deployment_package_evidence.json",
            ],
            commands,
        )

    def test_evidence_fails_closed_when_archive_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            inventory_path = Path(tmp) / "inventory.json"
            build_deployment_package_archive(
                Path("deploy/serverless/package.manifest.json"),
                root=Path("."),
                archive_path=Path(tmp) / "existing.zip",
                inventory_output_path=inventory_path,
            )
            missing_archive_path = Path(tmp) / "missing.zip"

            evidence = build_deployment_package_evidence(
                Path("deploy/serverless/package.manifest.json"),
                root=Path("."),
                archive_path=missing_archive_path,
                inventory_path=inventory_path,
                created_at="2026-06-15T00:41:00Z",
            )

        payload = evidence.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("failed", payload["status"])
        self.assertIsNone(payload["artifact_hashes"]["archive_sha256"])
        self.assertEqual("fail", payload["archive_verification"]["status"])
        self.assertFalse(checks["archive_sha256_present"]["passed"])
        self.assertFalse(checks["archive_verification_passed"]["passed"])
        self.assertTrue(checks["inventory_matches_plan"]["passed"])

    def test_evidence_fails_closed_when_inventory_does_not_match_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "package.zip"
            inventory_path = Path(tmp) / "inventory.json"
            build_deployment_package_archive(
                Path("deploy/serverless/package.manifest.json"),
                root=Path("."),
                archive_path=archive_path,
                inventory_output_path=inventory_path,
            )
            inventory_path.write_text(json.dumps({"status": "tampered"}), encoding="utf-8")

            evidence = build_deployment_package_evidence(
                Path("deploy/serverless/package.manifest.json"),
                root=Path("."),
                archive_path=archive_path,
                inventory_path=inventory_path,
                created_at="2026-06-15T00:42:00Z",
            )

        payload = evidence.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("failed", payload["status"])
        self.assertTrue(checks["archive_verification_passed"]["passed"])
        self.assertFalse(checks["inventory_matches_plan"]["passed"])

    def test_evidence_writer_and_command_write_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(__file__).resolve().parents[1]
            archive_path = Path(tmp) / "package.zip"
            inventory_path = Path(tmp) / "inventory.json"
            evidence_path = Path(tmp) / "evidence.json"
            build_deployment_package_archive(
                Path("deploy/serverless/package.manifest.json"),
                root=Path("."),
                archive_path=archive_path,
                inventory_output_path=inventory_path,
            )

            evidence = build_deployment_package_evidence(
                Path("deploy/serverless/package.manifest.json"),
                archive_path=archive_path,
                inventory_path=inventory_path,
                created_at="2026-06-15T00:43:00Z",
            )
            write_deployment_package_evidence(evidence, evidence_path)
            written_payload = json.loads(evidence_path.read_text(encoding="utf-8"))

            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/write_deployment_package_evidence.py",
                    "--manifest",
                    "deploy/serverless/package.manifest.json",
                    "--archive",
                    str(archive_path),
                    "--inventory",
                    str(inventory_path),
                    "--output",
                    str(evidence_path),
                    "--created-at",
                    "2026-06-15T00:44:00Z",
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            command_payload = json.loads(proc.stdout)
            file_payload = json.loads(evidence_path.read_text(encoding="utf-8"))

        self.assertEqual("complete", written_payload["status"])
        self.assertEqual(proc.stderr, "")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertEqual("complete", command_payload["status"])
        self.assertEqual(command_payload, file_payload)
        self.assertEqual("2026-06-15T00:44:00Z", file_payload["created_at"])


if __name__ == "__main__":
    unittest.main()
