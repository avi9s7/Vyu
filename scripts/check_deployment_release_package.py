from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vyu.deployment import (  # noqa: E402
    DeploymentReleasePackageError,
    build_deployment_release_package_checklist,
    write_deployment_release_package_checklist,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check local deployment release-package readiness from manifest, archive, inventory, and evidence artifacts."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("deploy/serverless/package.manifest.json"),
        help="Deployment package manifest JSON path.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Repository root used to resolve package paths.",
    )
    parser.add_argument(
        "--archive",
        type=Path,
        required=True,
        help="Built deployment archive path.",
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        required=True,
        help="Package inventory JSON path produced by the archive builder.",
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        required=True,
        help="Deployment package evidence JSON path.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output release-package checklist JSON path.",
    )
    parser.add_argument(
        "--created-at",
        help="Optional ISO-8601 timestamp to make tests and rehearsals deterministic.",
    )
    args = parser.parse_args()

    try:
        checklist = build_deployment_release_package_checklist(
            args.manifest,
            root=args.root,
            archive_path=args.archive,
            inventory_path=args.inventory,
            evidence_path=args.evidence,
            created_at=args.created_at,
        )
        write_deployment_release_package_checklist(checklist, args.output)
    except DeploymentReleasePackageError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(checklist.to_json(), indent=2, sort_keys=True))
    return 0 if checklist.status == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
