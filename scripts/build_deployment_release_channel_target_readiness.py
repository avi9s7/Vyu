from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vyu.deployment import (  # noqa: E402
    DEFAULT_RELEASE_CHANNEL_CANDIDATE_TARGET_FAMILIES,
    DEFAULT_RELEASE_CHANNEL_TARGET_HANDOFF_CHECKLIST,
    DEFAULT_RELEASE_CHANNEL_TARGET_READINESS_NAME,
    DeploymentReleaseChannelTargetReadinessError,
    build_deployment_release_channel_target_readiness_note,
    write_deployment_release_channel_target_readiness_note,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a local release-channel target-selection readiness note/environment handoff checklist."
    )
    parser.add_argument("--export-summary", type=Path, required=True, help="Deployment release-channel evidence export summary JSON path.")
    parser.add_argument("--root", type=Path, default=Path("."), help="Repository root used to resolve relative paths.")
    parser.add_argument("--readiness-name", default=DEFAULT_RELEASE_CHANNEL_TARGET_READINESS_NAME, help="Target-readiness note name to record.")
    parser.add_argument("--created-at", help="Explicit note timestamp for deterministic output.")
    parser.add_argument(
        "--target-family",
        action="append",
        dest="target_families",
        help="Candidate target family to record. Can be supplied multiple times. Defaults to local target-family placeholders.",
    )
    parser.add_argument(
        "--handoff-item",
        action="append",
        dest="handoff_items",
        help="Environment handoff checklist item. Can be supplied multiple times. Defaults to the local handoff checklist.",
    )
    parser.add_argument("--output", type=Path, required=True, help="Output deployment release-channel target-readiness JSON path.")
    args = parser.parse_args()

    try:
        note = build_deployment_release_channel_target_readiness_note(
            export_summary_path=args.export_summary,
            root=args.root,
            readiness_name=args.readiness_name,
            created_at=args.created_at,
            candidate_target_families=tuple(args.target_families) if args.target_families else DEFAULT_RELEASE_CHANNEL_CANDIDATE_TARGET_FAMILIES,
            handoff_checklist=tuple(args.handoff_items) if args.handoff_items else DEFAULT_RELEASE_CHANNEL_TARGET_HANDOFF_CHECKLIST,
        )
        write_deployment_release_channel_target_readiness_note(note, args.output)
    except (DeploymentReleaseChannelTargetReadinessError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(note.to_json(), indent=2, sort_keys=True))
    return 0 if note.status == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
