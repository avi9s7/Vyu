from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vyu.deployment import (  # noqa: E402
    DEFAULT_RELEASE_CHANNEL_EVIDENCE_INDEX_NAME,
    DeploymentReleaseChannelEvidenceIndexError,
    build_deployment_release_channel_evidence_index,
    write_deployment_release_channel_evidence_index,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a local release-channel evidence index from a ready publication manifest."
    )
    parser.add_argument("--publication", type=Path, required=True, help="Deployment release-channel publication manifest JSON path.")
    parser.add_argument("--root", type=Path, default=Path("."), help="Repository root used to resolve relative paths.")
    parser.add_argument("--index-name", default=DEFAULT_RELEASE_CHANNEL_EVIDENCE_INDEX_NAME, help="Evidence index name to record.")
    parser.add_argument("--created-at", help="Explicit index timestamp for deterministic output.")
    parser.add_argument("--output", type=Path, required=True, help="Output deployment release-channel evidence index JSON path.")
    args = parser.parse_args()

    try:
        index = build_deployment_release_channel_evidence_index(
            publication_path=args.publication,
            root=args.root,
            index_name=args.index_name,
            created_at=args.created_at,
        )
        write_deployment_release_channel_evidence_index(index, args.output)
    except (DeploymentReleaseChannelEvidenceIndexError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(index.to_json(), indent=2, sort_keys=True))
    return 0 if index.status == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
