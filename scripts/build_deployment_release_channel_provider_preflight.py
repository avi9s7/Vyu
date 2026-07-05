from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vyu.deployment import (  # noqa: E402
    DEFAULT_RELEASE_CHANNEL_PROVIDER_PREFLIGHT_NAME,
    DEFAULT_RELEASE_CHANNEL_PROVIDER_PREFLIGHT_NEXT_ACTIONS,
    DEFAULT_RELEASE_CHANNEL_PROVIDER_PLANNING_REQUIREMENTS,
    DeploymentReleaseChannelProviderPreflightError,
    build_deployment_release_channel_provider_preflight,
    write_deployment_release_channel_provider_preflight,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a local release-channel provider-planning preflight without provider configuration."
    )
    parser.add_argument("--target-decision", type=Path, required=True, help="Deployment release-channel target decision JSON path.")
    parser.add_argument("--root", type=Path, default=Path("."), help="Repository root used to resolve relative paths.")
    parser.add_argument("--preflight-name", default=DEFAULT_RELEASE_CHANNEL_PROVIDER_PREFLIGHT_NAME, help="Provider-planning preflight name to record.")
    parser.add_argument("--created-at", help="Explicit preflight timestamp for deterministic output.")
    parser.add_argument(
        "--planning-requirement",
        action="append",
        dest="planning_requirements",
        help="Provider-planning requirement to record. Can be supplied multiple times. Defaults to local planning requirements.",
    )
    parser.add_argument(
        "--next-action",
        action="append",
        dest="next_actions",
        help="Next action to record. Can be supplied multiple times. Defaults to local preflight next actions.",
    )
    parser.add_argument("--output", type=Path, required=True, help="Output deployment release-channel provider-preflight JSON path.")
    args = parser.parse_args()

    try:
        preflight = build_deployment_release_channel_provider_preflight(
            target_decision_path=args.target_decision,
            root=args.root,
            preflight_name=args.preflight_name,
            created_at=args.created_at,
            planning_requirements=tuple(args.planning_requirements) if args.planning_requirements else DEFAULT_RELEASE_CHANNEL_PROVIDER_PLANNING_REQUIREMENTS,
            next_actions=tuple(args.next_actions) if args.next_actions else DEFAULT_RELEASE_CHANNEL_PROVIDER_PREFLIGHT_NEXT_ACTIONS,
        )
        write_deployment_release_channel_provider_preflight(preflight, args.output)
    except (DeploymentReleaseChannelProviderPreflightError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(preflight.to_json(), indent=2, sort_keys=True))
    return 0 if preflight.status == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
