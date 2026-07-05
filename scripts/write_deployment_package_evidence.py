from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vyu.deployment import (  # noqa: E402
    DeploymentPackageEvidenceError,
    build_deployment_package_evidence,
    write_deployment_package_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write unsigned local integrity/provenance evidence for a built deployment archive."
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
        "--output",
        type=Path,
        required=True,
        help="Output evidence JSON path.",
    )
    parser.add_argument(
        "--created-at",
        help="Optional ISO-8601 timestamp to make tests and rehearsals deterministic.",
    )
    args = parser.parse_args()

    try:
        evidence = build_deployment_package_evidence(
            args.manifest,
            root=args.root,
            archive_path=args.archive,
            inventory_path=args.inventory,
            created_at=args.created_at,
        )
        write_deployment_package_evidence(evidence, args.output)
    except DeploymentPackageEvidenceError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(evidence.to_json(), indent=2, sort_keys=True))
    return 0 if evidence.status == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
