import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.vyu.deployment import (
    DEPLOYMENT_ENV_FILE_ENV_VAR,
    DeploymentPackagePlan,
    DeploymentPackagePlanError,
    build_deployment_package_plan,
    write_deployment_package_plan,
)


class DeploymentPackagePlanTests(unittest.TestCase):
    def test_checked_in_manifest_builds_deterministic_inventory(self):
        first = build_deployment_package_plan(
            Path("deploy/serverless/package.manifest.json"),
            root=Path("."),
        )
        second = build_deployment_package_plan(
            Path("deploy/serverless/package.manifest.json"),
            root=Path("."),
        )

        self.assertIsInstance(first, DeploymentPackagePlan)
        self.assertEqual(first.to_json(), second.to_json())
        payload = first.to_json()
        self.assertEqual("planned", payload["status"])
        self.assertEqual("apps.serverless.handler.handler", payload["handler"])
        self.assertEqual(DEPLOYMENT_ENV_FILE_ENV_VAR, payload["operator_config_env_var"])
        file_paths = [item["path"] for item in payload["files"]]
        self.assertEqual(sorted(file_paths), file_paths)
        self.assertIn("apps/serverless/handler.py", file_paths)
        self.assertIn("src/vyu/deployment/package_plan.py", file_paths)
        self.assertIn("config/deployment.local.example.env", file_paths)
        self.assertNotIn("config/deployment.local.env", file_paths)
        self.assertFalse(any("__pycache__" in path for path in file_paths))
        self.assertFalse(any(path.endswith(".pyc") for path in file_paths))
        self.assertGreater(payload["summary"]["file_count"], 10)
        self.assertGreater(payload["summary"]["total_bytes"], 0)

    def test_package_plan_excludes_local_secret_file_when_config_directory_is_included(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "config" / "deployment.local.example.env").write_text("example", encoding="utf-8")
            (root / "config" / "deployment.local.env").write_text("secret", encoding="utf-8")
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "package_name": "test-package",
                        "deployment_target": "serverless-http",
                        "runtime": "python3.11",
                        "handler": "apps.serverless.handler.handler",
                        "operator_config_env_var": DEPLOYMENT_ENV_FILE_ENV_VAR,
                        "operator_config_example": "config/deployment.local.example.env",
                        "include_paths": ["config"],
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

            plan = build_deployment_package_plan(manifest_path, root=root)

        payload = plan.to_json()
        self.assertEqual(["config/deployment.local.example.env"], [item["path"] for item in payload["files"]])
        self.assertEqual(["config/deployment.local.env"], payload["excluded_paths"])

    def test_package_plan_rejects_invalid_manifest(self):
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
                        "operator_config_env_var": DEPLOYMENT_ENV_FILE_ENV_VAR,
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

            with self.assertRaisesRegex(DeploymentPackagePlanError, "handler_importable"):
                build_deployment_package_plan(manifest_path, root=root)

    def test_write_package_plan_outputs_stable_json_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "inventory.json"
            plan = build_deployment_package_plan(
                Path("deploy/serverless/package.manifest.json"),
                root=Path("."),
            )
            write_deployment_package_plan(plan, output)

            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(plan.to_json(), payload)
        self.assertEqual("planned", payload["status"])

    def test_plan_command_prints_json_and_writes_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(__file__).resolve().parents[1]
            output = Path(tmp) / "inventory.json"
            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/plan_deployment_package.py",
                    "--manifest",
                    "deploy/serverless/package.manifest.json",
                    "--output",
                    str(output),
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )

            stdout_payload = json.loads(proc.stdout)
            output_payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(proc.stderr, "")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertEqual("planned", stdout_payload["status"])
        self.assertEqual(stdout_payload, output_payload)
        self.assertGreater(stdout_payload["summary"]["file_count"], 10)


if __name__ == "__main__":
    unittest.main()
