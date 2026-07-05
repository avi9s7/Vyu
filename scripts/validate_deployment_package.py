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
    validate_deployment_package_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate local deployment package metadata for the Vyu serverless entrypoint."
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
        help="Repository root used to resolve manifest paths.",
    )
    args = parser.parse_args()

    try:
        result = validate_deployment_package_manifest(args.manifest, root=args.root)
    except DeploymentPackageManifestError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    payload = result.to_json()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
