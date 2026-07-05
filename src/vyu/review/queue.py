from __future__ import annotations

from typing import TYPE_CHECKING

from src.vyu.authz import Action, AuthorizationPolicy, Principal
from src.vyu.review import (
    ReviewDecision,
    ReviewStatus,
    ReviewTask,
    decide_review,
)

if TYPE_CHECKING:
    from src.vyu.storage import ProductionScope, ProductionStorage


def list_review_queue(
    storage: ProductionStorage,
    principal: Principal,
    scope: ProductionScope,
    status: ReviewStatus | None = None,
    run_id: str | None = None,
    policy: AuthorizationPolicy | None = None,
) -> list[ReviewTask]:
    policy = policy or AuthorizationPolicy()
    policy.require(principal, Action.REVIEW_OUTPUT, scope)
    tasks = [
        task
        for task in storage.list_review_tasks(run_id=run_id)
        if task.scope.tenant_id == scope.tenant_id
        and task.scope.workspace_id == scope.workspace_id
    ]
    if status is not None:
        return [task for task in tasks if task.status == status]
    return tasks


def decide_queued_review_task(
    storage: ProductionStorage,
    principal: Principal,
    review_id: str,
    decision: ReviewDecision,
    comment: str,
    decided_at: str,
    audit_event_id: str,
    audit_created_at: str,
    policy: AuthorizationPolicy | None = None,
) -> ReviewTask:
    task = storage.get_review_task(review_id)
    decided = decide_review(
        principal=principal,
        task=task,
        decision=decision,
        comment=comment,
        decided_at=decided_at,
        policy=policy,
    )
    storage.record_review_decision(
        decided,
        audit_event_id=audit_event_id,
        audit_created_at=audit_created_at,
    )
    return decided
