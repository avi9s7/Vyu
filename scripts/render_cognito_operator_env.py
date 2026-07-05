#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Mapping


class CognitoOperatorEnvError(ValueError):
    """Raised when Terraform output JSON cannot be converted into Vyu env."""


_REQUIRED_OPERATOR_KEYS = (
    "VYU_AUTH_MODE",
    "VYU_TOKEN_ISSUER",
    "VYU_TOKEN_AUDIENCE",
    "VYU_OIDC_JWKS_URI",
    "VYU_OIDC_DISCOVERY_URI",
    "VYU_OIDC_ALLOWED_ALGORITHMS",
    "VYU_OIDC_REQUIRED_TOKEN_USE",
    "VYU_REQUIRE_EMAIL_VERIFIED",
    "VYU_REQUIRE_TENANT_GOVERNANCE",
)

_ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render Vyu operator .env settings from the AWS Cognito Terraform output JSON."
    )
    parser.add_argument(
        "--terraform-output-json",
        type=Path,
        required=True,
        help="Path to `terraform output -json` from deploy/aws/cognito.",
    )
    parser.add_argument(
        "--tenant-governance-registry",
        help="Optional VYU_TENANT_GOVERNANCE_REGISTRY value to include in the rendered env.",
    )
    parser.add_argument(
        "--sqlite-db",
        help="Optional VYU_SQLITE_DB value to include in the rendered env.",
    )
    parser.add_argument(
        "--phase-output-dir",
        help="Optional VYU_PHASE_OUTPUT_DIR value to include in the rendered env.",
    )
    parser.add_argument(
        "--tenant-id",
        help="Optional smoke/operator VYU_TENANT_ID value to include in the rendered env.",
    )
    parser.add_argument(
        "--workspace-id",
        help="Optional smoke/operator VYU_WORKSPACE_ID value to include in the rendered env.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write to this path instead of stdout.",
    )
    args = parser.parse_args(argv)

    try:
        env = render_operator_env(
            _read_json(args.terraform_output_json),
            tenant_governance_registry=args.tenant_governance_registry,
            sqlite_db=args.sqlite_db,
            phase_output_dir=args.phase_output_dir,
            tenant_id=args.tenant_id,
            workspace_id=args.workspace_id,
        )
    except CognitoOperatorEnvError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    text = format_env(env)
    if args.output is None:
        print(text, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    return 0


def render_operator_env(
    terraform_output: Mapping[str, object],
    *,
    tenant_governance_registry: str | None = None,
    sqlite_db: str | None = None,
    phase_output_dir: str | None = None,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
) -> dict[str, str]:
    raw_env = _terraform_output_value(terraform_output, "vyu_operator_env")
    if not isinstance(raw_env, Mapping):
        raise CognitoOperatorEnvError("Terraform output vyu_operator_env must be an object.")

    env = {str(key): str(value) for key, value in raw_env.items() if str(value).strip()}
    missing = [key for key in _REQUIRED_OPERATOR_KEYS if not env.get(key)]
    if missing:
        raise CognitoOperatorEnvError(
            "Terraform output vyu_operator_env is missing required keys: " + ", ".join(missing)
        )

    optional_values = {
        "VYU_TENANT_GOVERNANCE_REGISTRY": tenant_governance_registry,
        "VYU_SQLITE_DB": sqlite_db,
        "VYU_PHASE_OUTPUT_DIR": phase_output_dir,
        "VYU_TENANT_ID": tenant_id,
        "VYU_WORKSPACE_ID": workspace_id,
    }
    for key, value in optional_values.items():
        if value is not None and str(value).strip():
            env[key] = str(value).strip()

    return dict(sorted(env.items()))


def format_env(env: Mapping[str, str]) -> str:
    lines = ["# Generated from deploy/aws/cognito Terraform outputs. Do not commit secrets here."]
    for key in sorted(env):
        if not _ENV_KEY_RE.match(key):
            raise CognitoOperatorEnvError(f"Invalid environment variable name: {key}")
        lines.append(f"{key}={_quote_env_value(env[key])}")
    return "\n".join(lines) + "\n"


def _read_json(path: Path) -> Mapping[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CognitoOperatorEnvError(f"Could not read Terraform output JSON: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CognitoOperatorEnvError("Terraform output file is not valid JSON.") from exc
    if not isinstance(payload, Mapping):
        raise CognitoOperatorEnvError("Terraform output JSON must be an object.")
    return payload


def _terraform_output_value(terraform_output: Mapping[str, object], key: str) -> object:
    wrapped = terraform_output.get(key)
    if isinstance(wrapped, Mapping) and "value" in wrapped:
        return wrapped["value"]
    if wrapped is not None:
        return wrapped
    raise CognitoOperatorEnvError(f"Terraform output is missing {key}.")


def _quote_env_value(value: str) -> str:
    value = str(value)
    if value == "":
        return '""'
    if re.fullmatch(r"[A-Za-z0-9_./:@%+=,\-]+", value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


if __name__ == "__main__":
    raise SystemExit(main())
