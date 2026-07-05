import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from src.vyu.deployment import (
    DeploymentSmokeTestConfig,
    DeploymentSmokeTestError,
    DeploymentSmokeTestResult,
    run_deployment_smoke_test,
)


class DeploymentSmokeTestTests(unittest.TestCase):
    def test_smoke_test_passes_for_composed_local_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_deployment_smoke_test(_config(tmp), now=int(time.time()))

        payload = result.to_json()
        self.assertIsInstance(result, DeploymentSmokeTestResult)
        self.assertEqual("pass", payload["status"])
        self.assertEqual({"passed": 3, "failed": 0, "total": 3}, payload["summary"])
        self.assertEqual(
            ["health", "authenticated_review_queue", "fail_closed_bad_token"],
            [check["name"] for check in payload["checks"]],
        )
        self.assertTrue(all(check["passed"] for check in payload["checks"]))

    def test_smoke_test_reports_route_failure_without_hiding_other_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_deployment_smoke_test(
                _config(tmp, role="vyu:unknown-role"),
                now=int(time.time()),
            )

        payload = result.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("fail", payload["status"])
        self.assertTrue(checks["health"]["passed"])
        self.assertFalse(checks["authenticated_review_queue"]["passed"])
        self.assertEqual("identity_mapping_failed", checks["authenticated_review_queue"]["actual_reason"])
        self.assertTrue(checks["fail_closed_bad_token"]["passed"])

    def test_config_rejects_non_positive_token_lifetime(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = _config(tmp, token_lifetime_seconds=0)
            with self.assertRaisesRegex(DeploymentSmokeTestError, "token_lifetime_seconds"):
                config.validate()

    def test_smoke_test_command_prints_json_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(__file__).resolve().parents[1]
            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/smoke_test_deployment.py",
                    "--sqlite-db",
                    str(Path(tmp) / "production.sqlite"),
                    "--output-dir",
                    str(Path(tmp) / "outputs"),
                    "--issuer",
                    "https://issuer.example",
                    "--audience",
                    "vyu-api",
                    "--hs256-secret",
                    "test-secret",
                    "--tenant-id",
                    "tenant-a",
                    "--workspace-id",
                    "workspace-a",
                    "--user-id",
                    "smoke-user",
                    "--role",
                    "vyu:reviewer",
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
        self.assertEqual(3, payload["summary"]["passed"])

    def test_smoke_test_command_rejects_invalid_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(__file__).resolve().parents[1]
            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/smoke_test_deployment.py",
                    "--sqlite-db",
                    str(Path(tmp) / "production.sqlite"),
                    "--output-dir",
                    str(Path(tmp) / "outputs"),
                    "--issuer",
                    "https://issuer.example",
                    "--audience",
                    "vyu-api",
                    "--hs256-secret",
                    "test-secret",
                    "--tenant-id",
                    "tenant-a",
                    "--workspace-id",
                    "workspace-a",
                    "--token-lifetime-seconds",
                    "0",
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(2, proc.returncode)
        self.assertIn("token_lifetime_seconds", proc.stderr)


def _config(tmp, role="vyu:reviewer", token_lifetime_seconds=300):
    return DeploymentSmokeTestConfig(
        sqlite_db_path=Path(tmp) / "production.sqlite",
        phase_output_dir=Path(tmp) / "outputs",
        token_issuer="https://issuer.example",
        token_audience="vyu-api",
        hs256_secret="test-secret",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        user_id="smoke-user",
        role=role,
        token_lifetime_seconds=token_lifetime_seconds,
        request_id_prefix="unit-smoke",
    )


if __name__ == "__main__":
    unittest.main()
