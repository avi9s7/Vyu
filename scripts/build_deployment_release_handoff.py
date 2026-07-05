from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vyu.deployment import (  # noqa: E402
    DeploymentReleaseHandoffError,
    build_deployment_release_handoff_bundle,
    write_deployment_release_handoff_bundle,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a local deployment release handoff manifest from release evidence and review records."
    )
    parser.add_argument("--summary", type=Path, required=True, help="Deployment release evidence summary JSON path.")
    parser.add_argument("--review", type=Path, required=True, help="Deployment release review decision JSON path.")
    parser.add_argument("--created-at", help="Explicit handoff timestamp for deterministic output.")
    parser.add_argument("--output", type=Path, required=True, help="Output deployment release handoff JSON path.")
    args = parser.parse_args()

    try:
        bundle = build_deployment_release_handoff_bundle(
            summary_path=args.summary,
            review_path=args.review,
            created_at=args.created_at,
        )
        write_deployment_release_handoff_bundle(bundle, args.output)
    except (DeploymentReleaseHandoffError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(bundle.to_json(), indent=2, sort_keys=True))
    return 0 if bundle.status == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
