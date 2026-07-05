from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
import uuid

from src.vyu.privacy import (
    PrivacyApproval,
    PrivacyGate,
    PrivacyGateDecision,
    WorkflowDataUse,
)
from src.vyu.storage import PrivacyApprovalRecord, ProductionStorage


@dataclass(frozen=True)
class PrivacyApprovalResult:
    approval_id: str
    allowed: bool
    status: str
    reasons: tuple[str, ...]
    missing_approvals: tuple[str, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "approval_id": self.approval_id,
            "allowed": self.allowed,
            "status": self.status,
            "reasons": list(self.reasons),
            "missing_approvals": list(self.missing_approvals),
        }


def evaluate_privacy_workflow(
    run_id: str,
    tenant_id: str,
    workspace_id: str,
    data_use: WorkflowDataUse,
    storage: ProductionStorage | None = None,
    approval_id_factory: Callable[[str], str] | None = None,
    audit_event_id_factory: Callable[[str, str], str] | None = None,
    evaluated_at: str | None = None,
    gate: PrivacyGate | None = None,
) -> PrivacyApprovalResult:
    gate = gate or PrivacyGate()
    evaluated_at = evaluated_at or datetime.now(timezone.utc).isoformat()
    decision = gate.evaluate(data_use)
    approval_id = _approval_id(run_id, approval_id_factory)
    result = _result(approval_id, decision)

    if storage is not None:
        storage.record_privacy_approval(
            PrivacyApprovalRecord(
                approval_id=approval_id,
                run_id=run_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                purpose=data_use.purpose,
                data_classification=data_use.data_classification.value,
                decision_status=decision.status.value,
                allowed=decision.allowed,
                reasons=decision.reasons,
                missing_approvals=decision.missing_approvals,
                approvals=tuple(
                    _approval_payload(approval)
                    for approval in data_use.approvals
                ),
                created_at=evaluated_at,
            ),
            audit_event_id=_audit_event_id(
                run_id,
                "privacy_approval_recorded",
                audit_event_id_factory,
            ),
            audit_created_at=evaluated_at,
        )

    return result


def _result(
    approval_id: str,
    decision: PrivacyGateDecision,
) -> PrivacyApprovalResult:
    return PrivacyApprovalResult(
        approval_id=approval_id,
        allowed=decision.allowed,
        status=decision.status.value,
        reasons=decision.reasons,
        missing_approvals=decision.missing_approvals,
    )


def _approval_payload(approval: PrivacyApproval) -> dict[str, str]:
    return {
        "approval_type": approval.approval_type,
        "approved_by": approval.approved_by,
        "approved_at": approval.approved_at,
    }


def _approval_id(
    run_id: str,
    approval_id_factory: Callable[[str], str] | None,
) -> str:
    if approval_id_factory is not None:
        return approval_id_factory(run_id)
    return f"privacy-{run_id}-{uuid.uuid4().hex}"


def _audit_event_id(
    run_id: str,
    event_type: str,
    audit_event_id_factory: Callable[[str, str], str] | None,
) -> str:
    if audit_event_id_factory is not None:
        return audit_event_id_factory(run_id, event_type)
    return f"{run_id}-{event_type}-{uuid.uuid4().hex}"
