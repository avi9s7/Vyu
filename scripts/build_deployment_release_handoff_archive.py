from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vyu.deployment import (  # noqa: E402
    DeploymentReleaseHandoffArchiveError,
    build_deployment_release_handoff_archive_inventory,
    write_deployment_release_handoff_archive_inventory,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a deterministic local archive/inventory for deployment release handoff evidence."
    )
    parser.add_argument("--handoff", type=Path, required=True, help="Deployment release handoff JSON path.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Repository root used to resolve relative handoff artifact paths.",
    )
    parser.add_argument("--created-at", help="Explicit inventory timestamp for deterministic output.")
    parser.add_argument("--inventory", type=Path, required=True, help="Output handoff archive inventory JSON path.")
    parser.add_argument("--archive", type=Path, help="Optional deterministic handoff evidence zip archive path.")
    args = parser.parse_args()

    try:
        inventory = build_deployment_release_handoff_archive_inventory(
            handoff_path=args.handoff,
            root=args.root,
            created_at=args.created_at,
            archive_path=args.archive,
        )
        write_deployment_release_handoff_archive_inventory(inventory, args.inventory)
    except (DeploymentReleaseHandoffArchiveError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(inventory.to_json(), indent=2, sort_keys=True))
    return 0 if inventory.status == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
