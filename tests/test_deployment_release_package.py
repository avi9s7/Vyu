import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.vyu.deployment import (
    DEPLOYMENT_RELEASE_PACKAGE_CHECKLIST_SCHEMA,
    DeploymentReleasePackageChecklist,
    build_deployment_package_archive,
    build_deployment_package_evidence,
    build_deployment_release_package_checklist,
    write_deployment_package_evidence,
    write_deployment_release_package_checklist,
)


class DeploymentReleasePackageTests(unittest.TestCase):
    def _build_ready_artifacts(self, tmp: str):
        archive_path = Path(tmp) / "package.zip"
        inventory_path = Path(tmp) / "inventory.json"
        evidence_path = Path(tmp) / "evidence.json"
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
            created_at="2026-06-15T01:00:00Z",
        )
        write_deployment_package_evidence(evidence, evidence_path)
        return archive, archive_path, inventory_path, evidence_path

    def test_release_checklist_marks_ready_when_archive_inventory_and_evidence_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, archive_path, inventory_path, evidence_path = self._build_ready_artifacts(tmp)

            checklist = build_deployment_release_package_checklist(
                Path("deploy/serverless/package.manifest.json"),
                root=Path("."),
                archive_path=archive_path,
                inventory_path=inventory_path,
                evidence_path=evidence_path,
                created_at="2026-06-15T01:05:00Z",
            )

        payload = checklist.to_json()
        checks = {check["name"]: check for check in payload["checks"]}

        self.assertIsInstance(checklist, DeploymentReleasePackageChecklist)
        self.assertEqual(DEPLOYMENT_RELEASE_PACKAGE_CHECKLIST_SCHEMA, payload["schema_version"])
        self.assertEqual("ready", payload["status"])
        self.assertEqual("2026-06-15T01:05:00Z", payload["created_at"])
        self.assertEqual("vyu-local-serverless-entrypoint", payload["package"]["package_name"])
        self.assertEqual(archive.archive_sha256, payload["artifact_hashes"]["archive_sha256"])
        self.assertEqual(archive.inventory_sha256, payload["artifact_hashes"]["inventory_sha256"])
        self.assertRegex(payload["artifact_hashes"]["evidence_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(all(payload["required_command_coverage"].values()))
        self.assertEqual("pass", payload["archive_verification"]["status"])
        self.assertEqual("complete", payload["evidence"]["status"])
        self.assertTrue(checks["manifest_validation_passed"]["passed"])
        self.assertTrue(checks["required_command_coverage_complete"]["passed"])
        self.assertTrue(checks["archive_verification_passed"]["passed"])
        self.assertTrue(checks["inventory_matches_plan"]["passed"])
        self.assertTrue(checks["evidence_status_complete"]["passed"])
        self.assertTrue(checks["evidence_hashes_match_artifacts"]["passed"])

    def test_release_checklist_blocks_when_evidence_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, archive_path, inventory_path, _ = self._build_ready_artifacts(tmp)
            missing_evidence_path = Path(tmp) / "missing-evidence.json"

            checklist = build_deployment_release_package_checklist(
                Path("deploy/serverless/package.manifest.json"),
                root=Path("."),
                archive_path=archive_path,
                inventory_path=inventory_path,
                evidence_path=missing_evidence_path,
                created_at="2026-06-15T01:06:00Z",
            )

        payload = checklist.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("blocked", payload["status"])
        self.assertEqual("missing_or_invalid", payload["evidence"]["status"])
        self.assertFalse(checks["evidence_file_exists"]["passed"])
        self.assertFalse(checks["evidence_status_complete"]["passed"])
        self.assertFalse(checks["evidence_hashes_match_artifacts"]["passed"])

    def test_release_checklist_blocks_when_evidence_hashes_are_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, archive_path, inventory_path, evidence_path = self._build_ready_artifacts(tmp)
            payload = json.loads(evidence_path.read_text(encoding="utf-8"))
            payload["artifact_hashes"]["archive_sha256"] = "0" * 64
            evidence_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            checklist = build_deployment_release_package_checklist(
                Path("deploy/serverless/package.manifest.json"),
                root=Path("."),
                archive_path=archive_path,
                inventory_path=inventory_path,
                evidence_path=evidence_path,
                created_at="2026-06-15T01:07:00Z",
            )

        payload = checklist.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("blocked", payload["status"])
        self.assertTrue(checks["evidence_status_complete"]["passed"])
        self.assertFalse(checks["evidence_hashes_match_artifacts"]["passed"])

    def test_release_checklist_writer_and_command_write_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(__file__).resolve().parents[1]
            _, archive_path, inventory_path, evidence_path = self._build_ready_artifacts(tmp)
            output_path = Path(tmp) / "release-checklist.json"

            checklist = build_deployment_release_package_checklist(
                Path("deploy/serverless/package.manifest.json"),
                archive_path=archive_path,
                inventory_path=inventory_path,
                evidence_path=evidence_path,
                created_at="2026-06-15T01:08:00Z",
            )
            write_deployment_release_package_checklist(checklist, output_path)
            written_payload = json.loads(output_path.read_text(encoding="utf-8"))

            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/check_deployment_release_package.py",
                    "--manifest",
                    "deploy/serverless/package.manifest.json",
                    "--archive",
                    str(archive_path),
                    "--inventory",
                    str(inventory_path),
                    "--evidence",
                    str(evidence_path),
                    "--output",
                    str(output_path),
                    "--created-at",
                    "2026-06-15T01:09:00Z",
                ],
                cwd=root,
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
        self.assertEqual("2026-06-15T01:09:00Z", file_payload["created_at"])


if __name__ == "__main__":
    unittest.main()
