import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.vyu.deployment import (
    DeploymentCompositionConfig,
    DeploymentOperatorConfig,
    DeploymentOperatorConfigError,
    DeploymentSmokeTestConfig,
    load_deployment_operator_env,
    parse_env_text,
)


class DeploymentOperatorConfigTests(unittest.TestCase):
    def test_example_config_parses_only_when_placeholder_secret_is_allowed(self):
        path = Path("config/deployment.local.example.env")

        with self.assertRaisesRegex(DeploymentOperatorConfigError, "placeholder"):
            load_deployment_operator_env(path)

        config = load_deployment_operator_env(path, allow_placeholder_secret=True)
        summary = config.safe_summary()

        self.assertEqual("local_tenant", config.tenant_id)
        self.assertEqual("local_workspace", config.workspace_id)
        self.assertTrue(summary["hs256_secret_configured"])
        self.assertTrue(summary["hs256_secret_placeholder"])
        self.assertNotIn("__REPLACE_WITH_LOCAL_SECRET__", json.dumps(summary))

    def test_mapping_builds_composition_and_smoke_configs(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = DeploymentOperatorConfig.from_mapping(_mapping(tmp))

        composition = config.to_composition_config()
        smoke = config.to_smoke_test_config()

        self.assertIsInstance(composition, DeploymentCompositionConfig)
        self.assertIsInstance(smoke, DeploymentSmokeTestConfig)
        self.assertEqual("https://issuer.example", composition.token_issuer)
        self.assertEqual("vyu-api", composition.token_audience)
        self.assertEqual(("/v1/health", "/v1/status"), composition.unauthenticated_paths)
        self.assertFalse(composition.require_email_verified)
        self.assertEqual("tenant-a", smoke.tenant_id)
        self.assertEqual("workspace-a", smoke.workspace_id)
        self.assertEqual("vyu:reviewer", smoke.role)
        self.assertEqual(120, smoke.token_lifetime_seconds)


    def test_mapping_builds_oidc_operator_config_without_hs256_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            jwks = Path(tmp) / "jwks.json"
            jwks.write_text('{"keys":[{"kty":"RSA","kid":"k","n":"AQAB","e":"AQAB"}]}', encoding="utf-8")
            mapping = {
                **_mapping(tmp),
                "VYU_AUTH_MODE": "oidc_jwks",
                "VYU_HS256_SECRET": "",
                "VYU_OIDC_JWKS_FILE": str(jwks),
                "VYU_OIDC_REQUIRED_TOKEN_USE": "id",
            }
            config = DeploymentOperatorConfig.from_mapping(mapping)

        self.assertEqual("oidc_jwks", config.auth_mode)
        self.assertEqual(jwks, config.oidc_jwks_path)
        self.assertEqual("id", config.oidc_required_token_use)
        summary = config.safe_summary()
        self.assertFalse(summary["hs256_secret_configured"])
        self.assertEqual("oidc_jwks", summary["auth_mode"])

    def test_parser_supports_comments_export_and_quotes(self):
        values = parse_env_text(
            """
            # comment
            export VYU_TOKEN_ISSUER="https://issuer.example"
            VYU_TOKEN_AUDIENCE='vyu-api'
            VYU_ROLE=vyu:reviewer
            """
        )

        self.assertEqual("https://issuer.example", values["VYU_TOKEN_ISSUER"])
        self.assertEqual("vyu-api", values["VYU_TOKEN_AUDIENCE"])
        self.assertEqual("vyu:reviewer", values["VYU_ROLE"])

    def test_placeholder_secret_is_rejected_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            mapping = {**_mapping(tmp), "VYU_HS256_SECRET": "__REPLACE_WITH_LOCAL_SECRET__"}
            with self.assertRaisesRegex(DeploymentOperatorConfigError, "placeholder"):
                DeploymentOperatorConfig.from_mapping(mapping)

    def test_validate_command_rejects_placeholder_without_printing_secret(self):
        proc = subprocess.run(
            [
                sys.executable,
                "scripts/validate_deployment_config.py",
                "--env-file",
                "config/deployment.local.example.env",
            ],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(2, proc.returncode)
        self.assertIn("placeholder", proc.stderr)
        self.assertNotIn("__REPLACE_WITH_LOCAL_SECRET__", proc.stdout + proc.stderr)

    def test_validate_command_prints_safe_summary_for_real_local_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / "deployment.env"
            env_path.write_text(_env_text(tmp), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/validate_deployment_config.py",
                    "--env-file",
                    str(env_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(proc.stderr, "")
        self.assertEqual(0, proc.returncode, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual("valid", payload["status"])
        self.assertTrue(payload["config"]["hs256_secret_configured"])
        self.assertFalse(payload["config"]["hs256_secret_placeholder"])
        self.assertNotIn("real-local-secret", proc.stdout)


    def test_smoke_command_can_read_operator_env_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / "deployment.env"
            env_path.write_text(_env_text(tmp), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/smoke_test_deployment.py",
                    "--env-file",
                    str(env_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(proc.stderr, "")
        self.assertEqual(0, proc.returncode, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual("pass", payload["status"])
        self.assertEqual(3, payload["summary"]["passed"])

def _mapping(tmp):
    return {
        "VYU_SQLITE_DB": str(Path(tmp) / "production.sqlite"),
        "VYU_PHASE_OUTPUT_DIR": str(Path(tmp) / "outputs"),
        "VYU_TOKEN_ISSUER": "https://issuer.example",
        "VYU_TOKEN_AUDIENCE": "vyu-api",
        "VYU_HS256_SECRET": "real-local-secret",
        "VYU_TENANT_ID": "tenant-a",
        "VYU_WORKSPACE_ID": "workspace-a",
        "VYU_USER_ID": "reviewer-1",
        "VYU_ROLE": "vyu:reviewer",
        "VYU_TOKEN_LEEWAY_SECONDS": "10",
        "VYU_TOKEN_LIFETIME_SECONDS": "120",
        "VYU_UNAUTHENTICATED_PATHS": "/v1/health,/v1/status",
        "VYU_INITIALIZE_STORAGE": "true",
        "VYU_REQUIRE_EMAIL_VERIFIED": "false",
        "VYU_REQUEST_ID_PREFIX": "operator-test",
        "VYU_SERVERLESS_DEFAULT_REQUEST_ID": "serverless-test",
        "VYU_SERVERLESS_EXTRA_RESPONSE_HEADERS": "x-env=local",
    }


def _env_text(tmp):
    return "\n".join(f"{key}={value}" for key, value in _mapping(tmp).items()) + "\n"


if __name__ == "__main__":
    unittest.main()
