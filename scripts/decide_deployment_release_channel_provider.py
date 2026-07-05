from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vyu.deployment import (  # noqa: E402
    DEFAULT_RELEASE_CHANNEL_PROVIDER_DECISION_NEXT_ACTIONS,
    DEPLOYMENT_RELEASE_CHANNEL_PROVIDER_DECISIONS,
    DeploymentReleaseChannelProviderDecisionError,
    build_deployment_release_channel_provider_decision_record,
    write_deployment_release_channel_provider_decision_record,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record a local release-channel provider-planning decision without provider configuration."
    )
    parser.add_argument("--provider-preflight", type=Path, required=True, help="Deployment release-channel provider preflight JSON path.")
    parser.add_argument("--root", type=Path, default=Path("."), help="Repository root used to resolve relative paths.")
    parser.add_argument("--decision", required=True, choices=DEPLOYMENT_RELEASE_CHANNEL_PROVIDER_DECISIONS, help="Operator decision for provider planning.")
    parser.add_argument("--planning-track", help="Abstract provider-planning track. Required only when --decision proceed.")
    parser.add_argument("--operator-id", required=True, help="Operator identifier to record.")
    parser.add_argument("--operator-role", required=True, help="Operator role to record.")
    parser.add_argument("--rationale", required=True, help="Operator rationale for the decision.")
    parser.add_argument("--decided-at", help="Explicit decision timestamp for deterministic output.")
    parser.add_argument(
        "--next-action",
        action="append",
        dest="next_actions",
        help="Next action to record. Can be supplied multiple times. Defaults to local provider-decision next actions.",
    )
    parser.add_argument("--output", type=Path, required=True, help="Output deployment release-channel provider decision JSON path.")
    args = parser.parse_args()

    try:
        record = build_deployment_release_channel_provider_decision_record(
            provider_preflight_path=args.provider_preflight,
            root=args.root,
            decision=args.decision,
            provider_planning_track=args.planning_track,
            operator_id=args.operator_id,
            operator_role=args.operator_role,
            rationale=args.rationale,
            decided_at=args.decided_at,
            next_actions=tuple(args.next_actions) if args.next_actions else DEFAULT_RELEASE_CHANNEL_PROVIDER_DECISION_NEXT_ACTIONS,
        )
        write_deployment_release_channel_provider_decision_record(record, args.output)
    except (DeploymentReleaseChannelProviderDecisionError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(record.to_json(), indent=2, sort_keys=True))
    return 0 if record.status in {"approved", "deferred"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
