#!/usr/bin/env python3
"""Print GitHub CLI commands to wire CI variables from Terraform outputs."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


PILOT_AWS_ACCOUNT_ID = "123456789012"

PLACEHOLDER_VALUES = {
    "dev": {
        "plan_role": f"arn:aws:iam::{PILOT_AWS_ACCOUNT_ID}:role/vyu-dev-github-plan",
        "apply_role": f"arn:aws:iam::{PILOT_AWS_ACCOUNT_ID}:role/vyu-dev-github-apply",
        "build_role": f"arn:aws:iam::{PILOT_AWS_ACCOUNT_ID}:role/vyu-dev-github-build",
        "subnet_ids": "subnet-0aaa1111bbbb2222,subnet-0ccc3333dddd4444,subnet-0eee5555ffff6666",
        "migration_sg": "sg-0placeholdermigration",
        "app_base_url": "dev.app.vyu.example",
    },
    "staging": {
        "plan_role": f"arn:aws:iam::{PILOT_AWS_ACCOUNT_ID}:role/vyu-staging-github-plan",
        "apply_role": f"arn:aws:iam::{PILOT_AWS_ACCOUNT_ID}:role/vyu-staging-github-apply",
        "build_role": f"arn:aws:iam::{PILOT_AWS_ACCOUNT_ID}:role/vyu-staging-github-build",
        "subnet_ids": "subnet-0aaa1111bbbb2222,subnet-0ccc3333dddd4444,subnet-0eee5555ffff6666",
        "migration_sg": "sg-0placeholdermigration",
        "app_base_url": "staging.app.vyu.example",
    },
    "prod": {
        "plan_role": f"arn:aws:iam::{PILOT_AWS_ACCOUNT_ID}:role/vyu-prod-github-plan",
        "apply_role": f"arn:aws:iam::{PILOT_AWS_ACCOUNT_ID}:role/vyu-prod-github-apply",
        "build_role": f"arn:aws:iam::{PILOT_AWS_ACCOUNT_ID}:role/vyu-prod-github-build",
        "subnet_ids": "subnet-0aaa1111bbbb2222,subnet-0ccc3333dddd4444,subnet-0eee5555ffff6666",
        "migration_sg": "sg-0placeholdermigration",
        "app_base_url": "app.vyu.example",
    },
}


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
    parser.add_argument(
        "--placeholder",
        action="store_true",
        help="Emit pilot placeholder gh commands without terraform output.",
    )
    args = parser.parse_args()

    if args.placeholder:
        pilot = PLACEHOLDER_VALUES[args.environment]
        plan_role = pilot["plan_role"]
        apply_role = pilot["apply_role"]
        build_role = pilot["build_role"]
        subnet_ids = pilot["subnet_ids"]
        migration_sg = pilot["migration_sg"]
        app_base_url = pilot["app_base_url"]
    else:
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
