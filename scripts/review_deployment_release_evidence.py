from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vyu.deployment import (  # noqa: E402
    DEPLOYMENT_RELEASE_REVIEW_DECISIONS,
    DeploymentReleaseReviewError,
    build_deployment_release_review_decision,
    write_deployment_release_review_decision,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record a local deployment release evidence review decision."
    )
    parser.add_argument("--summary", type=Path, required=True, help="Deployment release evidence summary JSON path.")
    parser.add_argument("--decision", choices=DEPLOYMENT_RELEASE_REVIEW_DECISIONS, required=True)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--reviewer-role", required=True)
    parser.add_argument("--comment", required=True)
    parser.add_argument("--decided-at", help="Explicit decision timestamp for deterministic output.")
    parser.add_argument("--output", type=Path, required=True, help="Output deployment release review decision JSON path.")
    args = parser.parse_args()

    try:
        review = build_deployment_release_review_decision(
            summary_path=args.summary,
            decision=args.decision,
            reviewer_id=args.reviewer_id,
            reviewer_role=args.reviewer_role,
            comment=args.comment,
            decided_at=args.decided_at,
        )
        write_deployment_release_review_decision(review, args.output)
    except (DeploymentReleaseReviewError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(review.to_json(), indent=2, sort_keys=True))
    return 0 if review.status == "approved" else 1


if __name__ == "__main__":
    raise SystemExit(main())
