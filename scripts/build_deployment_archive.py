from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vyu.deployment import (  # noqa: E402
    DeploymentPackageArchiveError,
    DeploymentPackageManifestError,
    DeploymentPackagePlanError,
    build_deployment_package_archive,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a deterministic local deployment archive from the package plan."
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
        help="Output zip archive path.",
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        help="Optional JSON inventory output path.",
    )
    args = parser.parse_args()

    try:
        result = build_deployment_package_archive(
            args.manifest,
            root=args.root,
            archive_path=args.archive,
            inventory_output_path=args.inventory,
        )
    except (DeploymentPackageManifestError, DeploymentPackagePlanError, DeploymentPackageArchiveError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(result.to_json(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
