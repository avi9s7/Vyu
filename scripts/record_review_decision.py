from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vyu.authz import Principal, Role, WorkspaceMembership
from src.vyu.entrypoints import (
    ReviewQueueDecisionApiRequest,
    ReviewQueueDecisionPayload,
    handle_review_queue_decision_api,
)
from src.vyu.review import ReviewDecision
from src.vyu.storage import ProductionStorage


def record_review_decision(
    sqlite_db: Path,
    review_id: str,
    tenant_id: str,
    workspace_id: str,
    user_id: str,
    role: Role,
    decision: ReviewDecision,
    comment: str,
    decided_at: str,
) -> dict[str, Any]:
    storage = ProductionStorage(sqlite_db)
    response = handle_review_queue_decision_api(
        ReviewQueueDecisionApiRequest(
            request_id="record-review-decision",
            payload=ReviewQueueDecisionPayload(
                principal=Principal(
                    user_id=user_id,
                    memberships=(
                        WorkspaceMembership(
                            tenant_id=tenant_id,
                            workspace_id=workspace_id,
                            roles=(role,),
                        ),
                    ),
                ),
                review_id=review_id,
                decision=decision,
                comment=comment,
                decided_at=decided_at,
            ),
        ),
        storage=storage,
        audit_event_id_factory=_audit_event_id,
        audit_created_at=decided_at,
    )
    return {"status_code": response.status_code, **response.body}


def main() -> int:
    parser = argparse.ArgumentParser(description="Record a Vyu reviewer queue decision.")
    parser.add_argument("--sqlite-db", type=Path, required=True)
    parser.add_argument("--review-id", required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--role", choices=[role.value for role in Role], required=True)
    parser.add_argument("--decision", choices=[decision.value for decision in ReviewDecision], required=True)
    parser.add_argument("--comment", required=True)
    parser.add_argument("--decided-at", required=True)
    args = parser.parse_args()

    payload = record_review_decision(
        sqlite_db=args.sqlite_db,
        review_id=args.review_id,
        tenant_id=args.tenant_id,
        workspace_id=args.workspace_id,
        user_id=args.user_id,
        role=Role(args.role),
        decision=ReviewDecision(args.decision),
        comment=args.comment,
        decided_at=args.decided_at,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status_code"] == 200 else 1


def _audit_event_id(run_id: str, event_type: str) -> str:
    return f"{run_id}-{event_type}-{uuid.uuid4().hex}"


if __name__ == "__main__":
    raise SystemExit(main())
