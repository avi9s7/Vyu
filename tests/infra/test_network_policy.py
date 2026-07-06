from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NETWORK_MODULE = ROOT / "infra" / "terraform" / "modules" / "network"
KMS_MODULE = ROOT / "infra" / "terraform" / "modules" / "kms"
DEV_ENV = ROOT / "infra" / "terraform" / "environments" / "dev"

REQUIRED_INTERFACE_ENDPOINTS = (
    "ecr.api",
    "ecr.dkr",
    "logs",
    "secretsmanager",
    "sqs",
    "kms",
    "sts",
)

INGRESS_CIDR_PATTERN = re.compile(
    r"cidr_ipv4\s*=\s*\"0\.0\.0\.0/0\"",
    re.MULTILINE,
)
INGRESS_BLOCKS_PATTERN = re.compile(
    r"cidr_blocks\s*=\s*\[[^\]]*0\.0\.0\.0/0",
    re.MULTILINE,
)
PREFIX_LIST_INGRESS_PATTERN = re.compile(
    r"prefix_list_id\s*=\s*data\.aws_ec2_managed_prefix_list\.cloudfront_origin_facing\.id",
    re.MULTILINE,
)
KMS_ROTATION_PATTERN = re.compile(r"enable_key_rotation\s*=\s*true", re.MULTILINE)
WILDCARD_PRINCIPAL_PATTERN = re.compile(
    r"Principal\s*=\s*\{[^}]*\"AWS\"\s*:\s*\"\*\"",
    re.MULTILINE,
)


def _read_module_tf(module_dir: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(module_dir.glob("*.tf")))


def test_kms_keys_enable_rotation() -> None:
    content = _read_module_tf(KMS_MODULE)
    for purpose in ("data", "audit_archive", "secrets", "logs", "state"):
        assert purpose in content
    assert "enable_key_rotation     = true" in content
    assert 'resource "aws_kms_alias" "this"' in content


def test_kms_policies_avoid_wildcard_principals() -> None:
    content = _read_module_tf(KMS_MODULE)
    assert not WILDCARD_PRINCIPAL_PATTERN.search(content)


def test_network_declares_three_az_subnet_tiers() -> None:
    content = _read_module_tf(NETWORK_MODULE)
    assert 'resource "aws_subnet" "public"' in content
    assert 'resource "aws_subnet" "private"' in content
    assert 'resource "aws_subnet" "database"' in content
    assert "slice(data.aws_availability_zones.available.names, 0, 3)" in content


def test_network_declares_required_vpc_endpoints() -> None:
    content = _read_module_tf(NETWORK_MODULE)
    assert 'resource "aws_vpc_endpoint" "s3"' in content
    for service in REQUIRED_INTERFACE_ENDPOINTS:
        assert service in content


def test_alb_ingress_uses_cloudfront_prefix_list_only() -> None:
    security_groups = (NETWORK_MODULE / "security_groups.tf").read_text(encoding="utf-8")
    ingress_sections = security_groups.split('resource "aws_vpc_security_group_ingress_rule"')
    alb_sections = [section for section in ingress_sections if section.startswith(' "alb_')]
    assert alb_sections, "expected ALB ingress rules"
    for section in alb_sections:
        assert PREFIX_LIST_INGRESS_PATTERN.search(section)
        assert not INGRESS_CIDR_PATTERN.search(section)
        assert not INGRESS_BLOCKS_PATTERN.search(section)


def test_security_groups_avoid_open_ingress() -> None:
    security_groups = (NETWORK_MODULE / "security_groups.tf").read_text(encoding="utf-8")
    ingress_blocks = re.findall(
        r'resource "aws_vpc_security_group_ingress_rule" "[^"]+" \{[^}]+\}',
        security_groups,
        re.DOTALL,
    )
    assert ingress_blocks, "expected ingress rules"
    for block in ingress_blocks:
        assert not INGRESS_CIDR_PATTERN.search(block)
        assert not INGRESS_BLOCKS_PATTERN.search(block)


def test_dev_documents_single_nat_gateway_cost_exception() -> None:
    readme = (NETWORK_MODULE / "README.md").read_text(encoding="utf-8")
    dev_vars = (DEV_ENV / "terraform.tfvars.example").read_text(encoding="utf-8")
    assert "single_nat_gateway" in readme
    assert "single_nat_gateway   = true" in dev_vars


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


def test_plan_json_rejects_public_rds_and_open_s3_when_present() -> None:
    """Guardrails for later data-module plans when PLAN_JSON is supplied in CI."""
    plan_path = ROOT / "tests" / "infra" / "fixtures" / "plan_policy_guards.json"
    if not plan_path.is_file():
        return

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    for resource in plan.get("planned_values", {}).get("root_module", {}).get("resources", []):
        values = resource.get("values", {})
        resource_type = resource.get("type")
        if resource_type == "aws_db_instance":
            assert values.get("publicly_accessible") is False
        if resource_type == "aws_s3_bucket_public_access_block":
            assert values.get("block_public_acls") is True
            assert values.get("block_public_policy") is True
            assert values.get("ignore_public_acls") is True
            assert values.get("restrict_public_buckets") is True
