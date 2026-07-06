from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPUTE_MODULE = ROOT / "infra" / "terraform" / "modules" / "compute"
WEB_DOCKERFILE = ROOT / "deploy" / "docker" / "web.Dockerfile"
WEB_ENTRYPOINT = ROOT / "deploy" / "docker" / "web-entrypoint.sh"

DIGEST_PATTERN = re.compile(r"@sha256:[a-f0-9]{64}")
LATEST_PATTERN = re.compile(r":latest\b")
PASSWORD_LITERAL_PATTERN = re.compile(r"\bpassword\s*=\s*\"", re.IGNORECASE)


def _read_module_tf(module_dir: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(module_dir.glob("*.tf")))


def test_ecr_repositories_are_immutable_encrypted_and_scanned() -> None:
    content = _read_module_tf(COMPUTE_MODULE)
    assert 'resource "aws_ecr_repository" "this"' in content
    assert "image_tag_mutability = \"IMMUTABLE\"" in content
    assert "scan_on_push = true" in content
    assert 'encryption_type = "KMS"' in content
    assert 'resource "aws_ecr_lifecycle_policy" "this"' in content
    assert 'resource "aws_ecr_repository_policy" "this"' in content


def test_task_roles_are_distinct_per_workload() -> None:
    content = _read_module_tf(COMPUTE_MODULE)
    for workload in ("web", "api", "worker", "migration"):
        assert f'aws_iam_role.task["{workload}"]' in content or f'aws_iam_role.task["{workload}"].arn' in content
        assert f'data "aws_iam_policy_document" "task_{workload}"' in content or workload == "web"


def test_ecs_services_disable_public_ips_and_use_circuit_breakers() -> None:
    content = (COMPUTE_MODULE / "services.tf").read_text(encoding="utf-8")
    assert content.count("assign_public_ip = false") >= 3
    assert content.count("deployment_circuit_breaker") >= 3
    assert 'resource "aws_ecs_service" "web"' in content
    assert 'resource "aws_ecs_service" "api"' in content
    assert 'resource "aws_ecs_service" "worker"' in content
    assert 'resource "aws_ecs_service" "migration"' not in content


def test_task_definitions_use_image_digests_and_secret_arns() -> None:
    content = (COMPUTE_MODULE / "task_definitions.tf").read_text(encoding="utf-8")
    assert content.count("var.image_digests.") >= 3
    assert "valueFrom = var.secret_arns" in content
    assert "secrets" in content
    assert not LATEST_PATTERN.search(content)
    assert not PASSWORD_LITERAL_PATTERN.search(content)


def test_task_definitions_enable_readonly_root_and_non_root_user() -> None:
    content = (COMPUTE_MODULE / "task_definitions.tf").read_text(encoding="utf-8")
    assert "readonlyRootFilesystem = local.task_container_defaults.readonly_root_filesystem" in content
    assert '"10001:10001"' in content


def test_cloudwatch_log_groups_use_kms() -> None:
    content = (COMPUTE_MODULE / "logs.tf").read_text(encoding="utf-8")
    assert "kms_key_id        = var.logs_kms_key_arn" in content


def test_worker_autoscaling_tracks_queue_depth() -> None:
    content = (COMPUTE_MODULE / "autoscaling.tf").read_text(encoding="utf-8")
    assert 'resource "aws_appautoscaling_target" "worker"' in content
    assert 'resource "aws_appautoscaling_policy" "worker_queue_depth"' in content
    assert "ApproximateNumberOfMessagesVisible" in content


def test_migration_is_task_definition_only() -> None:
    content = _read_module_tf(COMPUTE_MODULE)
    assert 'resource "aws_ecs_task_definition" "migration"' in content
    assert 'resource "aws_ecs_service" "migration"' not in content


def test_web_dockerfile_is_non_root_and_rejects_fixture_mode() -> None:
    dockerfile = WEB_DOCKERFILE.read_text(encoding="utf-8")
    entrypoint = WEB_ENTRYPOINT.read_text(encoding="utf-8")
    assert "output: \"standalone\"" in (ROOT / "apps" / "web" / "next.config.mjs").read_text(encoding="utf-8")
    assert "USER vyu" in dockerfile
    assert DIGEST_PATTERN.search(dockerfile)
    assert "fixture mode must be disabled" in entrypoint
    instrumentation = (ROOT / "apps" / "web" / "instrumentation.ts").read_text(encoding="utf-8")
    assert "NEXT_PUBLIC_USE_FIXTURES=true is not allowed" in instrumentation


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
