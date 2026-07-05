from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vyu.authz import Principal, Role, WorkspaceMembership
from src.vyu.entrypoints import (
    ReviewQueueListApiRequest,
    ReviewQueueListPayload,
    handle_review_queue_list_api,
)
from src.vyu.review import ReviewStatus
from src.vyu.storage import ProductionStorage


def inspect_review_queue(
    sqlite_db: Path,
    tenant_id: str,
    workspace_id: str,
    user_id: str,
    role: Role,
    status: ReviewStatus | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    storage = ProductionStorage(sqlite_db)
    response = handle_review_queue_list_api(
        ReviewQueueListApiRequest(
            request_id="inspect-review-queue",
            payload=ReviewQueueListPayload(
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
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                status=status,
                run_id=run_id,
            ),
        ),
        storage=storage,
    )
    return {"status_code": response.status_code, **response.body}


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect Vyu persisted reviewer queue.")
    parser.add_argument("--sqlite-db", type=Path, required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--role", choices=[role.value for role in Role], required=True)
    parser.add_argument("--status", choices=[status.value for status in ReviewStatus])
    parser.add_argument("--run-id")
    args = parser.parse_args()

    payload = inspect_review_queue(
        sqlite_db=args.sqlite_db,
        tenant_id=args.tenant_id,
        workspace_id=args.workspace_id,
        user_id=args.user_id,
        role=Role(args.role),
        status=ReviewStatus(args.status) if args.status else None,
        run_id=args.run_id,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status_code"] == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
