import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.render_cognito_operator_env import (
    CognitoOperatorEnvError,
    format_env,
    render_operator_env,
)
from src.vyu.deployment import DeploymentOperatorConfig


ROOT = Path(__file__).resolve().parents[1]
COGNITO_DIR = ROOT / "deploy" / "aws" / "cognito"
IDENTITY_MODULE = ROOT / "infra" / "terraform" / "modules" / "identity"


class AwsCognitoProvisioningTests(unittest.TestCase):
    def test_terraform_stack_declares_cognito_identity_boundary(self):
        main = (IDENTITY_MODULE / "cognito.tf").read_text(encoding="utf-8")
        machine = (IDENTITY_MODULE / "machine_client.tf").read_text(encoding="utf-8")
        locals_tf = (IDENTITY_MODULE / "locals.tf").read_text(encoding="utf-8")
        variables = (IDENTITY_MODULE / "variables.tf").read_text(encoding="utf-8")
        outputs = (IDENTITY_MODULE / "outputs.tf").read_text(encoding="utf-8")
        wrapper = (COGNITO_DIR / "main.tf").read_text(encoding="utf-8")

        self.assertIn('resource "aws_cognito_user_pool" "vyu"', main)
        self.assertIn('resource "aws_cognito_user_pool_client" "web"', main)
        self.assertIn('resource "aws_cognito_user_pool_client" "machine"', machine)
        self.assertIn('resource "aws_cognito_resource_server" "vyu_api"', main)
        self.assertIn('resource "aws_cognito_user_group" "vyu_roles"', main)
        self.assertIn('resource "aws_cognito_identity_provider" "saml"', main)
        self.assertIn('resource "aws_cognito_identity_provider" "oidc"', main)
        self.assertIn("vyu_tenant_id", locals_tf)
        self.assertIn("vyu_workspace_id", locals_tf)
        self.assertIn("vyu_roles", locals_tf)
        self.assertIn('"custom:vyu_tenant_id"', locals_tf)
        self.assertIn('allowed_oauth_flows                  = ["code"]', main)
        self.assertIn('enable_token_revocation       = true', main)
        self.assertIn('prevent_user_existence_errors = "ENABLED"', main)
        self.assertIn('variable "saml_identity_providers"', variables)
        self.assertIn('variable "oidc_identity_providers"', variables)
        self.assertIn('output "vyu_operator_env"', outputs)
        self.assertIn('VYU_AUTH_MODE', outputs)
        self.assertIn('VYU_OIDC_JWKS_URI', outputs)
        self.assertIn('VYU_REQUIRE_TENANT_GOVERNANCE', outputs)
        self.assertIn('module "identity"', wrapper)

    def test_renderer_converts_terraform_outputs_to_operator_env(self):
        env = render_operator_env(
            _terraform_output(),
            tenant_governance_registry="/app/config/tenant-governance.json",
            sqlite_db="/app/data/production.sqlite",
            phase_output_dir="/app/outputs",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
        )

        self.assertEqual("oidc_jwks", env["VYU_AUTH_MODE"])
        self.assertEqual("client-123", env["VYU_TOKEN_AUDIENCE"])
        self.assertEqual("/app/config/tenant-governance.json", env["VYU_TENANT_GOVERNANCE_REGISTRY"])

        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "tenant-governance.json"
            registry.write_text('{"tenants": [], "workspaces": [], "grants": []}', encoding="utf-8")
            parsed = DeploymentOperatorConfig.from_mapping(
                {
                    **env,
                    "VYU_SQLITE_DB": str(Path(tmp) / "prod.sqlite"),
                    "VYU_PHASE_OUTPUT_DIR": str(Path(tmp) / "outputs"),
                    "VYU_TENANT_ID": "tenant-a",
                    "VYU_WORKSPACE_ID": "workspace-a",
                    "VYU_TENANT_GOVERNANCE_REGISTRY": str(registry),
                }
            )

        self.assertEqual("oidc_jwks", parsed.auth_mode)
        self.assertEqual("https://cognito-idp.us-east-1.amazonaws.com/us-east-1_ABC", parsed.token_issuer)
        self.assertEqual("id", parsed.oidc_required_token_use)

    def test_renderer_rejects_missing_required_operator_key(self):
        output = _terraform_output()
        del output["vyu_operator_env"]["value"]["VYU_OIDC_JWKS_URI"]

        with self.assertRaisesRegex(CognitoOperatorEnvError, "VYU_OIDC_JWKS_URI"):
            render_operator_env(output)

    def test_renderer_cli_writes_env_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "terraform-output.json"
            env_path = Path(tmp) / "deployment.cognito.env"
            output_path.write_text(json.dumps(_terraform_output()), encoding="utf-8")

            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/render_cognito_operator_env.py",
                    "--terraform-output-json",
                    str(output_path),
                    "--tenant-governance-registry",
                    "/app/config/tenant-governance.json",
                    "--output",
                    str(env_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual("", proc.stderr)
            self.assertEqual(0, proc.returncode, proc.stderr)
            text = env_path.read_text(encoding="utf-8")

        self.assertIn("VYU_AUTH_MODE=oidc_jwks", text)
        self.assertIn("VYU_OIDC_DISCOVERY_URI=https://cognito-idp.us-east-1.amazonaws.com/us-east-1_ABC/.well-known/openid-configuration", text)
        self.assertIn("VYU_TENANT_GOVERNANCE_REGISTRY=/app/config/tenant-governance.json", text)

    def test_env_formatter_quotes_values_safely(self):
        rendered = format_env({"VYU_SERVERLESS_EXTRA_RESPONSE_HEADERS": "x-env=prod, x-owner=platform team"})

        self.assertIn('VYU_SERVERLESS_EXTRA_RESPONSE_HEADERS="x-env=prod, x-owner=platform team"', rendered)


def _terraform_output():
    issuer = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_ABC"
    return {
        "vyu_operator_env": {
            "sensitive": False,
            "type": ["object"],
            "value": {
                "VYU_AUTH_MODE": "oidc_jwks",
                "VYU_TOKEN_ISSUER": issuer,
                "VYU_TOKEN_AUDIENCE": "client-123",
                "VYU_OIDC_JWKS_URI": f"{issuer}/.well-known/jwks.json",
                "VYU_OIDC_DISCOVERY_URI": f"{issuer}/.well-known/openid-configuration",
                "VYU_OIDC_ALLOWED_ALGORITHMS": "RS256",
                "VYU_OIDC_REQUIRED_TOKEN_USE": "id",
                "VYU_REQUIRE_EMAIL_VERIFIED": "true",
                "VYU_REQUIRE_TENANT_GOVERNANCE": "true",
                "VYU_IDENTITY_ACCESS_AUDIT_ENABLED": "true",
            },
        }
    }


if __name__ == "__main__":
    unittest.main()
