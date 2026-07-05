import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import zipfile

from src.vyu.deployment import (
    DeploymentPackageArchive,
    DeploymentPackageArchiveError,
    build_deployment_package_archive,
    build_deployment_package_plan,
    verify_deployment_package_archive,
)


class DeploymentPackageArchiveTests(unittest.TestCase):
    def test_archive_builder_writes_deterministic_zip_and_verifies_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            first_archive = Path(tmp) / "first.zip"
            second_archive = Path(tmp) / "second.zip"
            first = build_deployment_package_archive(
                Path("deploy/serverless/package.manifest.json"),
                root=Path("."),
                archive_path=first_archive,
            )
            second = build_deployment_package_archive(
                Path("deploy/serverless/package.manifest.json"),
                root=Path("."),
                archive_path=second_archive,
            )

            with zipfile.ZipFile(first_archive, "r") as archive:
                names = archive.namelist()

        self.assertIsInstance(first, DeploymentPackageArchive)
        self.assertEqual("built", first.to_json()["status"])
        self.assertEqual(first.archive_sha256, second.archive_sha256)
        self.assertEqual(first.inventory_sha256, second.inventory_sha256)
        self.assertTrue(first.verification.passed)
        self.assertIn("apps/serverless/handler.py", names)
        self.assertIn("src/vyu/deployment/package_archive.py", names)
        self.assertNotIn("config/deployment.local.env", names)
        self.assertFalse(any("__pycache__" in name or name.endswith(".pyc") for name in names))

    def test_archive_verification_fails_when_archive_has_extra_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "package.zip"
            plan = build_deployment_package_plan(
                Path("deploy/serverless/package.manifest.json"),
                root=Path("."),
            )
            build_deployment_package_archive(
                Path("deploy/serverless/package.manifest.json"),
                root=Path("."),
                archive_path=archive_path,
            )
            with zipfile.ZipFile(archive_path, "a") as archive:
                archive.writestr("unexpected.txt", "unexpected")

            verification = verify_deployment_package_archive(plan, archive_path=archive_path)

        checks = {check["name"]: check for check in verification.to_json()["checks"]}
        self.assertFalse(verification.passed)
        self.assertFalse(checks["entries_match_plan"]["passed"])
        self.assertFalse(checks["entry_hashes_match_plan"]["passed"])

    def test_archive_builder_rejects_invalid_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "config" / "deployment.local.example.env").write_text("example", encoding="utf-8")
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "package_name": "bad-package",
                        "deployment_target": "serverless-http",
                        "runtime": "python3.11",
                        "handler": "apps.serverless.handler.missing_handler",
                        "operator_config_env_var": "VYU_DEPLOYMENT_ENV_FILE",
                        "operator_config_example": "config/deployment.local.example.env",
                        "include_paths": ["config/deployment.local.example.env"],
                        "exclude_paths": ["config/deployment.local.env", "__pycache__", "*.pyc"],
                        "required_validation_commands": [
                            ["python", "scripts/validate_deployment_config.py"],
                            ["python", "scripts/validate_deployment_package.py"],
                            ["python", "scripts/smoke_test_deployment.py"],
                        ],
                        "infrastructure_managed_elsewhere": True,
                        "secret_values_in_manifest": False,
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(DeploymentPackageArchiveError, "handler_importable"):
                build_deployment_package_archive(
                    manifest_path,
                    root=root,
                    archive_path=root / "package.zip",
                )

    def test_archive_command_prints_json_writes_archive_and_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(__file__).resolve().parents[1]
            archive_path = Path(tmp) / "package.zip"
            inventory_path = Path(tmp) / "inventory.json"
            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/build_deployment_archive.py",
                    "--manifest",
                    "deploy/serverless/package.manifest.json",
                    "--archive",
                    str(archive_path),
                    "--inventory",
                    str(inventory_path),
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )

            payload = json.loads(proc.stdout)
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            archive_exists = archive_path.exists()

        self.assertEqual(proc.stderr, "")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertTrue(archive_exists)
        self.assertEqual("built", payload["status"])
        self.assertEqual("planned", inventory["status"])
        self.assertEqual(payload["summary"]["file_count"], inventory["summary"]["file_count"])
        self.assertEqual("pass", payload["verification"]["status"])
        self.assertRegex(payload["archive_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(payload["inventory_sha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
