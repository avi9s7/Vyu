from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TERRAFORM_ROOT = ROOT / "infra" / "terraform"

REQUIRED_MODULES = (
    "network",
    "kms",
    "data",
    "queues",
    "identity",
    "edge",
    "compute",
    "observability",
    "github_oidc",
)

REQUIRED_ENVIRONMENTS = ("dev", "staging", "prod")

FORBIDDEN_TF_PATTERNS = (
    re.compile(r"\bpassword\s*=", re.IGNORECASE),
    re.compile(r"\bapi[_-]?key\s*=", re.IGNORECASE),
    re.compile(r'backend\s+"local"', re.IGNORECASE),
)

REQUIRED_PROVIDER_CONSTRAINTS = (
    'required_version = ">= 1.9, < 2.0"',
    "hashicorp/aws",
    ">= 5.80, < 7.0",
    "hashicorp/random",
    "< 4",
    "hashicorp/tls",
    "< 5",
)


def _terraform_files() -> list[Path]:
    return sorted(TERRAFORM_ROOT.rglob("*.tf"))


def test_required_modules_exist() -> None:
    for module_name in REQUIRED_MODULES:
        module_dir = TERRAFORM_ROOT / "modules" / module_name
        assert module_dir.is_dir(), f"missing module directory: {module_name}"
        assert any(module_dir.glob("*.tf")), f"module has no .tf files: {module_name}"


def test_required_environments_exist() -> None:
    for environment in REQUIRED_ENVIRONMENTS:
        environment_dir = TERRAFORM_ROOT / "environments" / environment
        assert environment_dir.is_dir(), f"missing environment directory: {environment}"
        assert (environment_dir / "main.tf").is_file(), f"missing main.tf for {environment}"
        assert (environment_dir / "backend.hcl.example").is_file(), (
            f"missing backend.hcl.example for {environment}"
        )


def test_root_versions_tf_declares_provider_constraints() -> None:
    versions_tf = (TERRAFORM_ROOT / "versions.tf").read_text(encoding="utf-8")
    for fragment in REQUIRED_PROVIDER_CONSTRAINTS:
        assert fragment in versions_tf, f"versions.tf missing constraint fragment: {fragment}"


def test_environment_versions_match_policy() -> None:
    for environment in REQUIRED_ENVIRONMENTS:
        versions_tf = (
            TERRAFORM_ROOT / "environments" / environment / "versions.tf"
        ).read_text(encoding="utf-8")
        for fragment in REQUIRED_PROVIDER_CONSTRAINTS:
            assert fragment in versions_tf, (
                f"{environment}/versions.tf missing constraint fragment: {fragment}"
            )


def test_no_plaintext_secrets_or_local_backend_in_tf_files() -> None:
    violations: list[str] = []
    for path in _terraform_files():
        content = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_TF_PATTERNS:
            if pattern.search(content):
                violations.append(f"{path.relative_to(ROOT)} matches {pattern.pattern}")
    assert not violations, "forbidden Terraform patterns found:\n" + "\n".join(violations)


def test_backend_examples_use_remote_state_settings() -> None:
    for environment in REQUIRED_ENVIRONMENTS:
        backend_example = (
            TERRAFORM_ROOT / "environments" / environment / "backend.hcl.example"
        ).read_text(encoding="utf-8")
        for key in ("bucket", "key", "region", "encrypt", "kms_key_id"):
            assert f"{key}" in backend_example, (
                f"{environment} backend.hcl.example missing {key}"
            )
