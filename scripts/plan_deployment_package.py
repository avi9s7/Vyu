from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vyu.deployment import (  # noqa: E402
    DeploymentPackageManifestError,
    DeploymentPackagePlanError,
    build_deployment_package_plan,
    write_deployment_package_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a deterministic local deployment package inventory."
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
        "--output",
        type=Path,
        help="Optional JSON output path for the package inventory.",
    )
    args = parser.parse_args()

    try:
        plan = build_deployment_package_plan(args.manifest, root=args.root)
    except (DeploymentPackageManifestError, DeploymentPackagePlanError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    payload = plan.to_json()
    if args.output is not None:
        write_deployment_package_plan(plan, args.output)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
