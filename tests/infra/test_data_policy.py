from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_MODULE = ROOT / "infra" / "terraform" / "modules" / "data"
QUEUES_MODULE = ROOT / "infra" / "terraform" / "modules" / "queues"
CONFIGURE_SECRETS = ROOT / "scripts" / "configure_secrets.py"

SECRET_STRING_PATTERN = re.compile(
    r"aws_secretsmanager_secret_version|secret_string\s*=",
    re.IGNORECASE,
)
PASSWORD_LITERAL_PATTERN = re.compile(
    r"\bpassword\s*=\s*\"",
    re.IGNORECASE,
)


def _read_module_tf(module_dir: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(module_dir.glob("*.tf")))


def test_rds_is_private_and_encrypted() -> None:
    content = _read_module_tf(DATA_MODULE)
    assert 'resource "aws_db_instance" "postgres"' in content
    assert "publicly_accessible = false" in content
    assert "storage_encrypted     = true" in content
    assert "manage_master_user_password = true" in content


def test_rds_production_retention_and_multi_az() -> None:
    content = _read_module_tf(DATA_MODULE)
    assert "backup_retention_period   = local.is_production ? 35 : 7" in content
    assert "multi_az            = local.is_production" in content
    assert "deletion_protection     = local.is_production" in content


def test_s3_buckets_block_public_access_and_use_kms() -> None:
    content = _read_module_tf(DATA_MODULE)
    for bucket in ("evidence", "exports", "audit"):
        assert bucket in content
    assert 'resource "aws_s3_bucket_public_access_block" "application"' in content
    assert "restrict_public_buckets = true" in content
    assert "aws:SecureTransport" in content
    assert 'resource "aws_s3_bucket_object_lock_configuration" "audit"' in content


def test_queues_define_dlqs_and_redrive_policies() -> None:
    content = _read_module_tf(QUEUES_MODULE)
    for workload in ("ingestion", "research", "synthesis", "export"):
        assert workload in content
    assert 'resource "aws_sqs_queue" "dlq"' in content
    assert "maxReceiveCount     = 5" in content
    assert 'resource "aws_sqs_queue_redrive_allow_policy" "dlq"' in content
    assert "receive_wait_time_seconds  = 20" in content


def test_queue_cloudwatch_alarms_exist() -> None:
    content = _read_module_tf(QUEUES_MODULE)
    assert 'resource "aws_cloudwatch_metric_alarm" "queue_depth"' in content
    assert 'resource "aws_cloudwatch_metric_alarm" "queue_age"' in content
    assert 'resource "aws_cloudwatch_metric_alarm" "dlq_messages"' in content


def test_secrets_are_containers_without_versions() -> None:
    content = _read_module_tf(DATA_MODULE)
    assert 'resource "aws_secretsmanager_secret" "this"' in content
    assert not SECRET_STRING_PATTERN.search(content)


def test_terraform_modules_avoid_plaintext_secret_literals() -> None:
    violations: list[str] = []
    for module_dir in (DATA_MODULE, QUEUES_MODULE):
        for path in sorted(module_dir.rglob("*.tf")):
            content = path.read_text(encoding="utf-8")
            if PASSWORD_LITERAL_PATTERN.search(content):
                violations.append(str(path.relative_to(ROOT)))
    assert not violations


def test_configure_secrets_script_contract() -> None:
    content = CONFIGURE_SECRETS.read_text(encoding="utf-8")
    assert "--value-stdin" in content
    assert "--json-file" in content
    assert "put_secret_value" in content
    assert "Plaintext secret values on the command line are not allowed." in content


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


def test_plan_json_data_policy_guards_when_present() -> None:
    plan_path = ROOT / "tests" / "infra" / "fixtures" / "plan_data_policy_guards.json"
    if not plan_path.is_file():
        return

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    resources = plan.get("planned_values", {}).get("root_module", {}).get("resources", [])
    for resource in resources:
        resource_type = resource.get("type")
        values = resource.get("values", {})
        if resource_type == "aws_db_instance":
            assert values.get("publicly_accessible") is False
            assert values.get("storage_encrypted") is True
        if resource_type == "aws_s3_bucket_public_access_block":
            assert values.get("block_public_acls") is True
            assert values.get("restrict_public_buckets") is True
        if resource_type == "aws_sqs_queue" and values.get("name", "").endswith("-dlq"):
            continue
        if resource_type == "aws_sqs_queue":
            assert "redrive_policy" in values
