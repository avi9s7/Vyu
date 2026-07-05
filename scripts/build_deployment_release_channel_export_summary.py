from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vyu.deployment import (  # noqa: E402
    DEFAULT_RELEASE_CHANNEL_EXPORT_SUMMARY_NAME,
    DEFAULT_RELEASE_CHANNEL_REVIEW_CHECKLIST,
    DeploymentReleaseChannelExportSummaryError,
    build_deployment_release_channel_export_summary,
    write_deployment_release_channel_export_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a local release-channel evidence export summary/operator checklist."
    )
    parser.add_argument("--evidence-index", type=Path, required=True, help="Deployment release-channel evidence index JSON path.")
    parser.add_argument("--root", type=Path, default=Path("."), help="Repository root used to resolve relative paths.")
    parser.add_argument("--summary-name", default=DEFAULT_RELEASE_CHANNEL_EXPORT_SUMMARY_NAME, help="Export summary name to record.")
    parser.add_argument("--created-at", help="Explicit summary timestamp for deterministic output.")
    parser.add_argument(
        "--review-item",
        action="append",
        dest="review_items",
        help="Operator review checklist item. Can be supplied multiple times. Defaults to the local review checklist.",
    )
    parser.add_argument("--output", type=Path, required=True, help="Output deployment release-channel export summary JSON path.")
    args = parser.parse_args()

    try:
        summary = build_deployment_release_channel_export_summary(
            evidence_index_path=args.evidence_index,
            root=args.root,
            summary_name=args.summary_name,
            created_at=args.created_at,
            review_checklist=tuple(args.review_items) if args.review_items else DEFAULT_RELEASE_CHANNEL_REVIEW_CHECKLIST,
        )
        write_deployment_release_channel_export_summary(summary, args.output)
    except (DeploymentReleaseChannelExportSummaryError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(summary.to_json(), indent=2, sort_keys=True))
    return 0 if summary.status == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
