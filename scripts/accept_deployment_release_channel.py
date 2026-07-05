from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vyu.deployment import (  # noqa: E402
    DEPLOYMENT_RELEASE_CHANNEL_ACCEPTANCE_DECISIONS,
    DeploymentReleaseChannelAcceptanceError,
    build_deployment_release_channel_acceptance_record,
    write_deployment_release_channel_acceptance_record,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record a local deployment release-channel operator acceptance decision."
    )
    parser.add_argument("--preparation", type=Path, required=True, help="Deployment release-channel preparation JSON path.")
    parser.add_argument("--decision", choices=DEPLOYMENT_RELEASE_CHANNEL_ACCEPTANCE_DECISIONS, required=True)
    parser.add_argument("--operator-id", required=True)
    parser.add_argument("--operator-role", required=True)
    parser.add_argument("--comment", required=True)
    parser.add_argument("--decided-at", help="Explicit decision timestamp for deterministic output.")
    parser.add_argument("--root", type=Path, default=Path("."), help="Repository root used to resolve relative paths.")
    parser.add_argument("--output", type=Path, required=True, help="Output deployment release-channel acceptance JSON path.")
    args = parser.parse_args()

    try:
        record = build_deployment_release_channel_acceptance_record(
            preparation_path=args.preparation,
            decision=args.decision,
            operator_id=args.operator_id,
            operator_role=args.operator_role,
            comment=args.comment,
            decided_at=args.decided_at,
            root=args.root,
        )
        write_deployment_release_channel_acceptance_record(record, args.output)
    except (DeploymentReleaseChannelAcceptanceError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(record.to_json(), indent=2, sort_keys=True))
    return 0 if record.status == "accepted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
