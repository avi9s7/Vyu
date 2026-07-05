from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vyu.deployment import (  # noqa: E402
    DEFAULT_RELEASE_CHANNEL,
    DeploymentReleaseChannelPreparationError,
    build_deployment_release_channel_preparation,
    write_deployment_release_channel_preparation,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare a local release-channel provenance manifest from handoff archive inventory."
    )
    parser.add_argument("--inventory", type=Path, required=True, help="Deployment release handoff archive inventory JSON path.")
    parser.add_argument("--archive", type=Path, help="Optional handoff evidence archive zip path. Defaults to the path recorded in inventory when present.")
    parser.add_argument("--root", type=Path, default=Path("."), help="Repository root used to resolve relative paths.")
    parser.add_argument("--channel", default=DEFAULT_RELEASE_CHANNEL, help="Local release channel name to record.")
    parser.add_argument("--created-at", help="Explicit preparation timestamp for deterministic output.")
    parser.add_argument("--next-action", action="append", help="Operator-visible next action. May be supplied multiple times.")
    parser.add_argument("--output", type=Path, required=True, help="Output deployment release-channel preparation JSON path.")
    args = parser.parse_args()

    try:
        kwargs = {
            "inventory_path": args.inventory,
            "archive_path": args.archive,
            "root": args.root,
            "channel": args.channel,
            "created_at": args.created_at,
        }
        if args.next_action:
            kwargs["next_actions"] = tuple(args.next_action)
        preparation = build_deployment_release_channel_preparation(**kwargs)
        write_deployment_release_channel_preparation(preparation, args.output)
    except (DeploymentReleaseChannelPreparationError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(preparation.to_json(), indent=2, sort_keys=True))
    return 0 if preparation.status == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
