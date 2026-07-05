from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vyu.deployment import (  # noqa: E402
    DeploymentReleaseEvidenceError,
    build_deployment_release_evidence_summary,
    write_deployment_release_evidence_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a local deployment release evidence summary from package, checklist, and transcript evidence."
    )
    parser.add_argument("--package-evidence", type=Path, required=True, help="Deployment package evidence JSON path.")
    parser.add_argument("--release-checklist", type=Path, required=True, help="Deployment release-package checklist JSON path.")
    parser.add_argument("--transcript-bundle", type=Path, required=True, help="Deployment transcript bundle JSON path.")
    parser.add_argument("--created-at", help="Explicit summary timestamp for deterministic output.")
    parser.add_argument("--output", type=Path, required=True, help="Output release evidence summary JSON path.")
    args = parser.parse_args()

    try:
        summary = build_deployment_release_evidence_summary(
            package_evidence_path=args.package_evidence,
            release_checklist_path=args.release_checklist,
            transcript_bundle_path=args.transcript_bundle,
            created_at=args.created_at,
        )
        write_deployment_release_evidence_summary(summary, args.output)
    except (DeploymentReleaseEvidenceError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(summary.to_json(), indent=2, sort_keys=True))
    return 0 if summary.status == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
