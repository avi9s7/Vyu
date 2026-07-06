from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GITHUB_OIDC_MODULE = ROOT / "infra" / "terraform" / "modules" / "github_oidc"
WORKFLOWS = ROOT / ".github" / "workflows"
INFRA_PLAN_WORKFLOW = WORKFLOWS / "infra-plan.yml"
DEPLOY_WORKFLOW = WORKFLOWS / "deploy.yml"

ACTION_SHA_PATTERN = re.compile(r"uses:\s+[\w./-]+@([0-9a-f]{40})\b")
MUTABLE_ACTION_TAG_PATTERN = re.compile(r"uses:\s+[\w./-]+@v[\d.]")
STATIC_AWS_SECRET_PATTERN = re.compile(
    r"(AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|aws-access-key-id|aws-secret-access-key)",
    re.IGNORECASE,
)
BROAD_OIDC_SUBJECT_PATTERN = re.compile(
    r"repo:\$\{var\.github_repository\}:(\*|ref:\*)",
)
FORBIDDEN_APPLY_ON_PR_PATTERN = re.compile(r"terraform\s+apply", re.IGNORECASE)
JOB_BLOCK_PATTERN = re.compile(
    r"^  (?P<name>[\w-]+):\n(?P<body>(?:    .*\n?)*)",
    re.MULTILINE,
)


def _read_module_tf(module_dir: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(module_dir.glob("*.tf")))


def _read_workflow(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _workflow_job(workflow_content: str, job_name: str) -> str:
    for match in JOB_BLOCK_PATTERN.finditer(workflow_content):
        if match.group("name") == job_name:
            return match.group("body")
    raise AssertionError(f"job {job_name} not found in workflow")


def test_github_oidc_trust_policies_scope_repository_branch_and_environment() -> None:
    content = _read_module_tf(GITHUB_OIDC_MODULE)
    plan_section = content.split('data "aws_iam_policy_document" "plan_trust"')[1].split(
        'data "aws_iam_policy_document" "apply_trust"'
    )[0]
    apply_section = content.split('data "aws_iam_policy_document" "apply_trust"')[1].split(
        'data "aws_iam_policy_document" "build_trust"'
    )[0]
    build_section = content.split('data "aws_iam_policy_document" "build_trust"')[1]

    assert 'variable = "token.actions.githubusercontent.com:aud"' in content
    assert "repo:${var.github_repository}:pull_request" in plan_section
    assert "repo:${var.github_repository}:ref:refs/heads/main" in plan_section
    assert "repo:${var.github_repository}:ref:refs/heads/cursor/*" in plan_section
    assert (
        'values   = ["repo:${var.github_repository}:environment:${var.environment}"]'
        in apply_section
    )
    assert "repo:${var.github_repository}:environment:${var.environment}" in build_section
    assert not BROAD_OIDC_SUBJECT_PATTERN.search(content)


def test_apply_role_is_environment_scoped_not_pull_request() -> None:
    content = _read_module_tf(GITHUB_OIDC_MODULE)
    apply_section = content.split('data "aws_iam_policy_document" "apply_trust"')[1].split(
        'data "aws_iam_policy_document" "build_trust"'
    )[0]
    assert "pull_request" not in apply_section


def test_build_and_apply_policies_are_least_privilege() -> None:
    content = _read_module_tf(GITHUB_OIDC_MODULE)
    build_policy = content.split('data "aws_iam_policy_document" "build"')[1].split(
        'resource "aws_iam_role_policy" "build"'
    )[0]
    apply_policy = content.split('data "aws_iam_policy_document" "apply"')[1].split(
        'resource "aws_iam_role_policy" "apply"'
    )[0]
    assert "ecr:PutImage" in build_policy
    assert "local.ecr_repository_arns" in build_policy
    assert "ecs:UpdateService" in apply_policy
    assert "local.ecs_service_arns" in apply_policy


def test_environments_wire_github_oidc_before_compute() -> None:
    for environment in ("dev", "staging", "prod"):
        main_tf = (
            ROOT / "infra" / "terraform" / "environments" / environment / "main.tf"
        ).read_text(encoding="utf-8")
        github_index = main_tf.index('module "github_oidc"')
        compute_index = main_tf.index('module "compute"')
        assert github_index < compute_index
        assert "ecr_push_role_arns              = [module.github_oidc.build_role_arn]" in main_tf


def test_workflows_pin_actions_by_sha() -> None:
    for workflow in (INFRA_PLAN_WORKFLOW, DEPLOY_WORKFLOW):
        content = _read_workflow(workflow)
        assert not MUTABLE_ACTION_TAG_PATTERN.search(content), workflow.name
        shas = ACTION_SHA_PATTERN.findall(content)
        assert shas, workflow.name
        assert all(len(sha) == 40 for sha in shas)


def test_workflows_do_not_use_static_aws_keys() -> None:
    for workflow in (INFRA_PLAN_WORKFLOW, DEPLOY_WORKFLOW):
        content = _read_workflow(workflow)
        assert not STATIC_AWS_SECRET_PATTERN.search(content), workflow.name
        assert "role-to-assume:" in content


def test_infra_plan_workflow_is_plan_only_on_pull_requests() -> None:
    content = _read_workflow(INFRA_PLAN_WORKFLOW)
    assert "pull_request:" in content
    assert "terraform plan" in content
    assert not FORBIDDEN_APPLY_ON_PR_PATTERN.search(content)

    plan_job = _workflow_job(content, "plan")
    policy_job = _workflow_job(content, "policy")
    assert "id-token: write" in plan_job
    assert "id-token" not in policy_job


def test_deploy_workflow_requires_reviewed_plan_and_environment() -> None:
    content = _read_workflow(DEPLOY_WORKFLOW)
    assert "workflow_dispatch:" in content
    assert "terraform-plan-metadata-" in content
    assert "Verify commit SHA alignment" in content
    assert "terraform apply" in content
    assert "environment: ${{ inputs.environment }}" in content

    for job_name in ("build-images", "migrate", "apply", "rollback"):
        assert "id-token: write" in _workflow_job(content, job_name)


def test_deploy_workflow_runs_migration_before_apply_and_records_rollback() -> None:
    content = _read_workflow(DEPLOY_WORKFLOW)
    apply_job = _workflow_job(content, "apply")
    migrate_job = _workflow_job(content, "migrate")
    build_job = _workflow_job(content, "build-images")
    smoke_job = _workflow_job(content, "smoke")
    rollback_job = _workflow_job(content, "rollback")

    assert "needs: build-images" in migrate_job
    assert "needs: migrate" in apply_job
    assert "needs: apply" in smoke_job
    assert "needs: smoke" in rollback_job
    assert "if: failure()" in rollback_job
    assert "tasks-stopped" in content
    assert "exitCode" in content
    assert "force-new-deployment" in content
    assert "rollback-evidence.json" in content


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
