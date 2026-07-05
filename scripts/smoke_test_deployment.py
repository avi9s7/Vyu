from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vyu.deployment import (  # noqa: E402
    DeploymentCompositionError,
    DeploymentOperatorConfigError,
    DeploymentSmokeTestConfig,
    DeploymentSmokeTestError,
    load_deployment_operator_env,
    run_deployment_smoke_test,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run local smoke checks against the composed Vyu deployment graph."
    )
    parser.add_argument("--env-file", type=Path, help="Optional .env-style operator config file.")
    parser.add_argument("--sqlite-db", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--issuer")
    parser.add_argument("--audience")
    parser.add_argument("--hs256-secret")
    parser.add_argument("--tenant-id")
    parser.add_argument("--workspace-id")
    parser.add_argument("--user-id", default="smoke-user")
    parser.add_argument("--role", default="vyu:reviewer")
    parser.add_argument("--token-lifetime-seconds", type=int, default=300)
    parser.add_argument("--request-id-prefix", default="smoke")
    parser.add_argument("--tenant-governance-registry", type=Path)
    parser.add_argument("--require-tenant-governance", action="store_true")
    parser.add_argument("--api-key-auth-enabled", action="store_true")
    parser.add_argument("--api-key-issuer", default="vyu-api-key")
    parser.add_argument("--disable-identity-access-audit", action="store_true")
    args = parser.parse_args()

    try:
        config = _config_from_args(args)
        result = run_deployment_smoke_test(config)
    except (DeploymentCompositionError, DeploymentOperatorConfigError, DeploymentSmokeTestError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    payload = result.to_json()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "pass" else 1


def _config_from_args(args: argparse.Namespace) -> DeploymentSmokeTestConfig:
    if args.env_file is not None:
        return load_deployment_operator_env(args.env_file).to_smoke_test_config()
    missing = [
        name
        for name, value in {
            "--sqlite-db": args.sqlite_db,
            "--output-dir": args.output_dir,
            "--issuer": args.issuer,
            "--audience": args.audience,
            "--hs256-secret": args.hs256_secret,
            "--tenant-id": args.tenant_id,
            "--workspace-id": args.workspace_id,
        }.items()
        if value is None or str(value).strip() == ""
    ]
    if missing:
        raise DeploymentSmokeTestError(
            "Missing smoke-test CLI settings: " + ", ".join(missing)
        )
    return DeploymentSmokeTestConfig(
        sqlite_db_path=args.sqlite_db,
        phase_output_dir=args.output_dir,
        token_issuer=args.issuer,
        token_audience=args.audience,
        hs256_secret=args.hs256_secret,
        tenant_id=args.tenant_id,
        workspace_id=args.workspace_id,
        user_id=args.user_id,
        role=args.role,
        token_lifetime_seconds=args.token_lifetime_seconds,
        request_id_prefix=args.request_id_prefix,
        tenant_governance_registry_path=args.tenant_governance_registry,
        require_tenant_governance=args.require_tenant_governance,
        api_key_auth_enabled=args.api_key_auth_enabled,
        api_key_issuer=args.api_key_issuer,
        identity_access_audit_enabled=not args.disable_identity_access_audit,
    )


if __name__ == "__main__":
    raise SystemExit(main())
