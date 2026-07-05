from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from src.vyu.authz import Action, AuthorizationPolicy, Principal, ResourceScope
from src.vyu.governance.box import GovernanceBox


class ReviewStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


@dataclass(frozen=True)
class ReviewRecord:
    reviewer_id: str
    decision: ReviewDecision
    comment: str
    decided_at: str

    def to_json(self) -> dict[str, str]:
        return {
            "reviewer_id": self.reviewer_id,
            "decision": self.decision.value,
            "comment": self.comment,
            "decided_at": self.decided_at,
        }

    @classmethod
    def from_json(cls, payload: dict[str, str]) -> "ReviewRecord":
        return cls(
            reviewer_id=str(payload["reviewer_id"]),
            decision=ReviewDecision(str(payload["decision"])),
            comment=str(payload["comment"]),
            decided_at=str(payload["decided_at"]),
        )


@dataclass(frozen=True)
class ReviewTask:
    review_id: str
    run_id: str
    scope: ResourceScope
    status: ReviewStatus
    reason: str
    created_at: str
    decision: ReviewRecord | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "review_id": self.review_id,
            "run_id": self.run_id,
            "scope": {
                "tenant_id": self.scope.tenant_id,
                "workspace_id": self.scope.workspace_id,
            },
            "status": self.status.value,
            "reason": self.reason,
            "created_at": self.created_at,
            "decision": self.decision.to_json() if self.decision else None,
        }

    @classmethod
    def from_json(cls, payload: dict[str, object]) -> "ReviewTask":
        scope_payload = dict(payload["scope"])  # type: ignore[arg-type]
        decision_payload = payload.get("decision")
        return cls(
            review_id=str(payload["review_id"]),
            run_id=str(payload["run_id"]),
            scope=ResourceScope(
                tenant_id=str(scope_payload["tenant_id"]),
                workspace_id=str(scope_payload["workspace_id"]),
            ),
            status=ReviewStatus(str(payload["status"])),
            reason=str(payload["reason"]),
            created_at=str(payload["created_at"]),
            decision=(
                ReviewRecord.from_json(dict(decision_payload))
                if decision_payload is not None
                else None
            ),
        )


@dataclass(frozen=True)
class ExportGateDecision:
    allowed: bool
    reason: str


def create_review_task(
    run_id: str,
    governance_box: GovernanceBox,
    tenant_id: str,
    workspace_id: str,
    created_at: str,
) -> ReviewTask:
    status = (
        ReviewStatus.PENDING
        if governance_box.human_review_required
        else ReviewStatus.NOT_REQUIRED
    )
    return ReviewTask(
        review_id=f"review-{run_id}",
        run_id=run_id,
        scope=ResourceScope(tenant_id=tenant_id, workspace_id=workspace_id),
        status=status,
        reason=governance_box.human_review_reason,
        created_at=created_at,
    )


def decide_review(
    principal: Principal,
    task: ReviewTask,
    decision: ReviewDecision,
    comment: str,
    decided_at: str,
    policy: AuthorizationPolicy | None = None,
) -> ReviewTask:
    policy = policy or AuthorizationPolicy()
    policy.require(principal, Action.REVIEW_OUTPUT, task.scope)
    status = (
        ReviewStatus.APPROVED
        if decision == ReviewDecision.APPROVE
        else ReviewStatus.REJECTED
    )
    return ReviewTask(
        review_id=task.review_id,
        run_id=task.run_id,
        scope=task.scope,
        status=status,
        reason=task.reason,
        created_at=task.created_at,
        decision=ReviewRecord(
            reviewer_id=principal.user_id,
            decision=decision,
            comment=comment,
            decided_at=decided_at,
        ),
    )


def evaluate_export_gate(
    principal: Principal,
    task: ReviewTask,
    policy: AuthorizationPolicy | None = None,
) -> ExportGateDecision:
    policy = policy or AuthorizationPolicy()
    export_decision = policy.authorize(principal, Action.EXPORT_REPORT, task.scope)
    if not export_decision.allowed:
        return ExportGateDecision(allowed=False, reason="export_not_authorized")
    if task.status == ReviewStatus.NOT_REQUIRED:
        return ExportGateDecision(allowed=True, reason="review_not_required")
    if task.status == ReviewStatus.APPROVED:
        return ExportGateDecision(allowed=True, reason="review_approved")
    if task.status == ReviewStatus.REJECTED:
        return ExportGateDecision(allowed=False, reason="review_rejected")
    return ExportGateDecision(allowed=False, reason="review_required")


from src.vyu.review.queue import decide_queued_review_task, list_review_queue

__all__ = [
    "ExportGateDecision",
    "ReviewDecision",
    "ReviewRecord",
    "ReviewStatus",
    "ReviewTask",
    "create_review_task",
    "decide_queued_review_task",
    "decide_review",
    "evaluate_export_gate",
    "list_review_queue",
]
