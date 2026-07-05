import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.vyu.deployment import (
    DEPLOYMENT_ENV_FILE_ENV_VAR,
    DeploymentPackageManifest,
    DeploymentPackageManifestError,
    read_deployment_package_manifest,
    validate_deployment_package_manifest,
)


class DeploymentPackageManifestTests(unittest.TestCase):
    def test_checked_in_manifest_validates_package_metadata(self):
        result = validate_deployment_package_manifest(
            Path("deploy/serverless/package.manifest.json"),
            root=Path("."),
        )

        payload = result.to_json()
        self.assertEqual("pass", payload["status"])
        self.assertEqual("vyu-local-serverless-entrypoint", payload["package_name"])
        self.assertEqual(9, payload["summary"]["passed"])
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertTrue(checks["handler_importable"]["passed"])
        self.assertTrue(checks["local_secret_config_excluded"]["passed"])
        self.assertTrue(checks["secret_values_not_in_manifest"]["passed"])

    def test_manifest_round_trips_paths_and_commands(self):
        manifest = read_deployment_package_manifest(Path("deploy/serverless/package.manifest.json"))

        payload = manifest.to_json()

        self.assertIsInstance(manifest, DeploymentPackageManifest)
        self.assertEqual("apps.serverless.handler.handler", payload["handler"])
        self.assertIn("apps/serverless/handler.py", payload["include_paths"])
        self.assertIn("config/deployment.local.env", payload["exclude_paths"])
        self.assertIn(
            ["python", "scripts/validate_deployment_package.py", "--manifest", "deploy/serverless/package.manifest.json"],
            payload["required_validation_commands"],
        )

    def test_manifest_reports_non_importable_handler_without_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "config" / "deployment.local.example.env").write_text("# example\n", encoding="utf-8")
            manifest = DeploymentPackageManifest.from_mapping(
                {
                    **_valid_manifest_mapping(),
                    "handler": "apps.serverless.handler.missing_handler",
                    "include_paths": ["config/deployment.local.example.env"],
                }
            )

            result = manifest.validate(root=root, manifest_path=root / "manifest.json")

        payload = result.to_json()
        self.assertEqual("fail", payload["status"])
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertFalse(checks["handler_importable"]["passed"])

    def test_manifest_rejects_missing_required_fields(self):
        mapping = _valid_manifest_mapping()
        del mapping["handler"]

        with self.assertRaisesRegex(DeploymentPackageManifestError, "handler"):
            DeploymentPackageManifest.from_mapping(mapping)

    def test_manifest_requires_local_secret_exclusion_and_external_infrastructure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "config" / "deployment.local.example.env").write_text("# example\n", encoding="utf-8")
            manifest = DeploymentPackageManifest.from_mapping(
                {
                    **_valid_manifest_mapping(),
                    "include_paths": ["config/deployment.local.example.env"],
                    "exclude_paths": ["upstreams"],
                    "infrastructure_managed_elsewhere": False,
                    "secret_values_in_manifest": True,
                }
            )

            result = manifest.validate(root=root, manifest_path=root / "manifest.json")

        checks = {check["name"]: check for check in result.to_json()["checks"]}
        self.assertFalse(checks["local_secret_config_excluded"]["passed"])
        self.assertFalse(checks["infrastructure_managed_elsewhere"]["passed"])
        self.assertFalse(checks["secret_values_not_in_manifest"]["passed"])

    def test_validate_package_script_prints_json_and_exits_zero(self):
        root = Path(__file__).resolve().parents[1]
        proc = subprocess.run(
            [
                sys.executable,
                "scripts/validate_deployment_package.py",
                "--manifest",
                "deploy/serverless/package.manifest.json",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.stderr, "")
        self.assertEqual(0, proc.returncode, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual("pass", payload["status"])
        self.assertEqual("vyu-local-serverless-entrypoint", payload["package_name"])

    def test_validate_package_script_returns_nonzero_for_failed_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(__file__).resolve().parents[1]
            manifest_path = Path(tmp) / "manifest.json"
            manifest_path.write_text(
                json.dumps({**_valid_manifest_mapping(), "operator_config_env_var": "WRONG_ENV_VAR"}),
                encoding="utf-8",
            )
            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/validate_deployment_package.py",
                    "--manifest",
                    str(manifest_path),
                    "--root",
                    str(root),
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(1, proc.returncode)
        payload = json.loads(proc.stdout)
        self.assertEqual("fail", payload["status"])
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertFalse(checks["operator_config_env_var"]["passed"])


def _valid_manifest_mapping():
    return {
        "schema_version": 1,
        "package_name": "vyu-test-package",
        "deployment_target": "serverless-http",
        "runtime": "python3.11",
        "handler": "apps.serverless.handler.handler",
        "operator_config_env_var": DEPLOYMENT_ENV_FILE_ENV_VAR,
        "operator_config_example": "config/deployment.local.example.env",
        "include_paths": ["apps/serverless/handler.py", "config/deployment.local.example.env"],
        "exclude_paths": ["config/deployment.local.env", "upstreams"],
        "required_validation_commands": [
            ["python", "scripts/validate_deployment_config.py", "--env-file", "config/deployment.local.env"],
            ["python", "scripts/validate_deployment_package.py", "--manifest", "deploy/serverless/package.manifest.json"],
            ["python", "scripts/smoke_test_deployment.py", "--env-file", "config/deployment.local.env"],
        ],
        "infrastructure_managed_elsewhere": True,
        "secret_values_in_manifest": False,
        "notes": ["test manifest"],
    }


if __name__ == "__main__":
    unittest.main()
