#!/usr/bin/env python3
"""Print GitHub CLI commands to wire CI variables from Terraform outputs."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _terraform_output(environment: str) -> dict[str, dict[str, str]]:
    root = Path(__file__).resolve().parents[1]
    env_dir = root / "infra" / "terraform" / "environments" / environment
    if not env_dir.is_dir():
        raise SystemExit(f"Unknown environment directory: {env_dir}")

    result = subprocess.run(
        ["terraform", "-chdir", str(env_dir), "output", "-json"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(
            "terraform output failed. Run `terraform init` and `terraform apply` first."
        )
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "environment",
        choices=["dev", "staging", "prod"],
        help="Terraform environment whose outputs should be rendered.",
    )
    parser.add_argument(
        "--repo",
        default="avi9s7/Vyu",
        help="GitHub repository slug for gh variable set.",
    )
    args = parser.parse_args()

    outputs = _terraform_output(args.environment)

    def value(name: str) -> str:
        try:
            return outputs[name]["value"]
        except KeyError as exc:
            raise SystemExit(f"Missing terraform output: {name}") from exc

    plan_role = value("github_plan_role_arn")
    apply_role = value("github_apply_role_arn")
    build_role = value("github_build_role_arn")
    subnet_ids = value("private_subnet_ids_csv")
    migration_sg = value("migration_security_group_id")
    app_base_url = value("app_base_url")

    print("# Repository variable (infra-plan workflow; dev plan role)")
    print(f'gh variable set AWS_PLAN_ROLE_ARN --repo {args.repo} --body "{plan_role}"')
    print()
    print(f"# GitHub environment variables for `{args.environment}` (deploy workflow)")
    print(
        f'gh variable set AWS_APPLY_ROLE_ARN --repo {args.repo} '
        f'--env {args.environment} --body "{apply_role}"'
    )
    print(
        f'gh variable set AWS_BUILD_ROLE_ARN --repo {args.repo} '
        f'--env {args.environment} --body "{build_role}"'
    )
    print(
        f'gh variable set AWS_PRIVATE_SUBNET_IDS --repo {args.repo} '
        f'--env {args.environment} --body "{subnet_ids}"'
    )
    print(
        f'gh variable set AWS_MIGRATION_SECURITY_GROUP_ID --repo {args.repo} '
        f'--env {args.environment} --body "{migration_sg}"'
    )
    print(
        f'gh variable set APP_BASE_URL --repo {args.repo} '
        f'--env {args.environment} --body "{app_base_url}"'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
