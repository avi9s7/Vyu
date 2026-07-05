from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vyu.deployment import (  # noqa: E402
    DEFAULT_RELEASE_CHANNEL_PUBLICATION_CHANNEL,
    DeploymentReleaseChannelPublicationError,
    build_deployment_release_channel_publication_manifest,
    write_deployment_release_channel_publication_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare a local release-channel publication manifest from an accepted release-channel record."
    )
    parser.add_argument("--acceptance", type=Path, required=True, help="Deployment release-channel acceptance JSON path.")
    parser.add_argument("--root", type=Path, default=Path("."), help="Repository root used to resolve relative paths.")
    parser.add_argument("--publication-channel", default=DEFAULT_RELEASE_CHANNEL_PUBLICATION_CHANNEL, help="Local publication channel name to record.")
    parser.add_argument("--created-at", help="Explicit manifest timestamp for deterministic output.")
    parser.add_argument("--publication-step", action="append", help="Operator-visible publication checklist step. May be supplied multiple times.")
    parser.add_argument("--local-only-limit", action="append", help="Local-only safety limit to record. May be supplied multiple times.")
    parser.add_argument("--output", type=Path, required=True, help="Output deployment release-channel publication manifest JSON path.")
    args = parser.parse_args()

    try:
        kwargs = {
            "acceptance_path": args.acceptance,
            "root": args.root,
            "publication_channel": args.publication_channel,
            "created_at": args.created_at,
        }
        if args.publication_step:
            kwargs["publication_steps"] = tuple(args.publication_step)
        if args.local_only_limit:
            kwargs["local_only_limits"] = tuple(args.local_only_limit)
        manifest = build_deployment_release_channel_publication_manifest(**kwargs)
        write_deployment_release_channel_publication_manifest(manifest, args.output)
    except (DeploymentReleaseChannelPublicationError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(manifest.to_json(), indent=2, sort_keys=True))
    return 0 if manifest.status == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
