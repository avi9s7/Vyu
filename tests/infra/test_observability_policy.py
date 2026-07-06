from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OBSERVABILITY_MODULE = ROOT / "infra" / "terraform" / "modules" / "observability"
COMPUTE_MODULE = ROOT / "infra" / "terraform" / "modules" / "compute"
LOGGING_MODULE = ROOT / "src" / "vyu" / "observability" / "logging.py"

REQUIRED_ALARMS = (
    "alb_5xx",
    "alb_latency",
    "ecs_cpu",
    "ecs_memory",
    "rds_connections",
    "rds_storage",
    "rds_latency",
    "rds_failover",
    "queue_depth",
    "queue_age",
    "dlq_messages",
    "cognito_auth_failures",
    "waf_blocks",
    "job_failures",
    "connector_failures",
    "model_latency",
    "model_cost",
    "audit_failures",
    "backup_status",
)

REQUIRED_LOG_GROUPS = ("web", "api", "worker", "migration")


def _read_module_tf(module_dir: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(module_dir.glob("*.tf")))


def test_otel_collector_configuration_is_published() -> None:
    content = _read_module_tf(OBSERVABILITY_MODULE)
    assert 'resource "aws_ssm_parameter" "otel_collector_config"' in content
    assert "awsxray" in content
    assert "awsemf" in content


def test_sns_alarm_topics_are_encrypted() -> None:
    content = (OBSERVABILITY_MODULE / "sns.tf").read_text(encoding="utf-8")
    assert 'resource "aws_sns_topic" "alarms"' in content
    assert 'resource "aws_sns_topic" "critical"' in content
    assert "kms_master_key_id = var.logs_kms_key_arn" in content


def test_critical_alarms_require_production_acknowledgement() -> None:
    variables = (OBSERVABILITY_MODULE / "variables.tf").read_text(encoding="utf-8")
    assert "critical_alarm_owner_acknowledged" in variables
    assert 'var.environment != "prod" || var.critical_alarm_owner_acknowledged' in variables


def test_dashboard_and_alarms_cover_required_signals() -> None:
    content = _read_module_tf(OBSERVABILITY_MODULE)
    assert 'resource "aws_cloudwatch_dashboard" "operations"' in content
    for alarm in REQUIRED_ALARMS:
        assert f'"{alarm}"' in content or alarm in content


def test_alarms_route_to_sns_action_targets() -> None:
    content = (OBSERVABILITY_MODULE / "alarms.tf").read_text(encoding="utf-8")
    assert "alarm_actions       = local.alarm_actions_critical" in content
    assert "alarm_actions       = local.alarm_actions_standard" in content


def test_service_log_groups_use_kms_in_compute_module() -> None:
    content = _read_module_tf(COMPUTE_MODULE)
    assert "kms_key_id        = var.logs_kms_key_arn" in content
    assert 'resource "aws_cloudwatch_log_group" "service"' in content
    for workload in REQUIRED_LOG_GROUPS:
        assert workload in content


def test_application_logging_redacts_sensitive_fields() -> None:
    logging_py = LOGGING_MODULE.read_text(encoding="utf-8")
    config_py = (ROOT / "src" / "vyu" / "observability" / "config.py").read_text(encoding="utf-8")
    assert "RedactingJsonFormatter" in logging_py
    assert "authorization" in config_py
    assert "request_body" in config_py
    assert "token" in config_py


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
