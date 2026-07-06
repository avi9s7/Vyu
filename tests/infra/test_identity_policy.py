from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IDENTITY_MODULE = ROOT / "infra" / "terraform" / "modules" / "identity"
DEV_ENV = ROOT / "infra" / "terraform" / "environments" / "dev"
PROD_ENV = ROOT / "infra" / "terraform" / "environments" / "prod"
COGNITO_WRAPPER = ROOT / "deploy" / "aws" / "cognito"

PASSWORD_AUTH_PATTERN = re.compile(
    r"ALLOW_(ADMIN_)?USER_PASSWORD_AUTH",
    re.MULTILINE,
)
IMPLICIT_FLOW_PATTERN = re.compile(r"\"implicit\"", re.IGNORECASE)
SENSITIVE_OUTPUT_PATTERN = re.compile(
    r'output\s+"machine_client_secret"[\s\S]*?sensitive\s*=\s*true',
    re.MULTILINE,
)
REQUIRED_SCOPES = (
    "research.read",
    "research.write",
    "review.write",
    "export.write",
    "admin.write",
)


def _read_module_tf(module_dir: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(module_dir.glob("*.tf")))


def test_web_client_uses_authorization_code_flow_only() -> None:
    content = _read_module_tf(IDENTITY_MODULE)
    web_section = content.split('resource "aws_cognito_user_pool_client" "web"')[1]
    assert 'allowed_oauth_flows                  = ["code"]' in web_section
    assert not IMPLICIT_FLOW_PATTERN.search(web_section)


def test_password_grant_is_disabled() -> None:
    content = _read_module_tf(IDENTITY_MODULE)
    assert not PASSWORD_AUTH_PATTERN.search(content)


def test_production_mfa_is_required() -> None:
    content = (IDENTITY_MODULE / "locals.tf").read_text(encoding="utf-8")
    assert 'mfa_configuration     = local.is_production ? "ON"' in content


def test_browser_client_is_public_and_machine_client_is_confidential() -> None:
    content = _read_module_tf(IDENTITY_MODULE)
    web_section = content.split('resource "aws_cognito_user_pool_client" "web"')[1].split(
        'resource "aws_cognito_user_pool_client" "machine"'
    )[0]
    machine_section = content.split('resource "aws_cognito_user_pool_client" "machine"')[1]
    assert "generate_secret                      = false" in web_section
    assert "generate_secret                      = true" in machine_section


def test_machine_client_uses_narrow_scopes() -> None:
    locals_tf = (IDENTITY_MODULE / "locals.tf").read_text(encoding="utf-8")
    assert "machine_allowed_oauth_scopes" in locals_tf
    assert "research.read" in locals_tf
    assert "export.write" in locals_tf
    assert "admin.write" not in locals_tf.split("machine_allowed_oauth_scopes")[1].split("supported_identity_providers")[0]


def test_api_resource_server_declares_required_scopes() -> None:
    content = _read_module_tf(IDENTITY_MODULE)
    for scope in REQUIRED_SCOPES:
        assert scope in content


def test_callback_urls_must_be_https() -> None:
    variables = (IDENTITY_MODULE / "variables.tf").read_text(encoding="utf-8")
    assert 'startswith(url, "https://")' in variables


def test_environment_tfvars_use_https_environment_specific_callbacks() -> None:
    for environment in ("dev", "staging", "prod"):
        tfvars = (
            ROOT / "infra" / "terraform" / "environments" / environment / "terraform.tfvars.example"
        ).read_text(encoding="utf-8")
        assert environment in tfvars
        assert "https://" in tfvars
        assert "identity_callback_urls" in tfvars
        assert "identity_logout_urls" in tfvars


def test_custom_attributes_documented_as_hints_only() -> None:
    content = (IDENTITY_MODULE / "locals.tf").read_text(encoding="utf-8")
    assert "PostgreSQL membership" in content
    assert "authentication hints" in content


def test_refresh_token_rotation_enabled_for_clients() -> None:
    content = _read_module_tf(IDENTITY_MODULE)
    assert content.count('feature                    = "ENABLED"') >= 2
    assert "refresh_token_rotation" in content


def test_sensitive_machine_client_secret_output() -> None:
    outputs = (IDENTITY_MODULE / "outputs.tf").read_text(encoding="utf-8")
    assert SENSITIVE_OUTPUT_PATTERN.search(outputs)


def test_cognito_wrapper_delegates_to_composed_identity_module() -> None:
    wrapper_main = (COGNITO_WRAPPER / "main.tf").read_text(encoding="utf-8")
    assert 'source = "../../../infra/terraform/modules/identity"' in wrapper_main
    assert 'module "identity"' in wrapper_main


def test_terraform_validate_dev_environment() -> None:
    init = subprocess.run(
        ["terraform", "-chdir=infra/terraform/environments/dev", "init", "-backend=false"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert init.returncode == 0, init.stderr

    validate = subprocess.run(
        ["terraform", "-chdir=infra/terraform/environments/dev", "validate"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert validate.returncode == 0, validate.stderr
