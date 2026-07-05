from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from src.vyu.sources import ProductionSourceRecord


class DataClassification(StrEnum):
    PUBLIC_LITERATURE = "public_literature"
    LICENSED_CONTENT = "licensed_content"
    CUSTOMER_DOCUMENT = "customer_document"
    PII = "pii"
    PHI = "phi"
    EPHI = "ephi"


class PrivacyReviewStatus(StrEnum):
    APPROVED = "approved"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class PrivacyApproval:
    approval_type: str
    approved_by: str
    approved_at: str

    @property
    def complete(self) -> bool:
        return bool(self.approval_type and self.approved_by and self.approved_at)


@dataclass(frozen=True)
class WorkflowDataUse:
    purpose: str
    data_classification: DataClassification
    sources: tuple[ProductionSourceRecord, ...] = ()
    approvals: tuple[PrivacyApproval, ...] = ()


@dataclass(frozen=True)
class PrivacyGateDecision:
    status: PrivacyReviewStatus
    reasons: tuple[str, ...] = ()
    missing_approvals: tuple[str, ...] = ()

    @property
    def allowed(self) -> bool:
        return self.status == PrivacyReviewStatus.APPROVED

    def to_json(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "allowed": self.allowed,
            "reasons": list(self.reasons),
            "missing_approvals": list(self.missing_approvals),
        }


class PrivacyGate:
    def evaluate(self, data_use: WorkflowDataUse) -> PrivacyGateDecision:
        reasons: list[str] = []
        required_approvals: set[str] = set()

        if _contains_phi_or_ephi(data_use):
            reasons.append("PHI/ePHI requires approved privacy clearance.")
            required_approvals.update({"privacy", "security"})

        if data_use.purpose == "patient_specific_recommendation":
            reasons.append(
                "Patient-specific recommendations require regulatory and clinical safety clearance."
            )
            required_approvals.update({"regulatory", "clinical_safety"})

        if data_use.purpose == "model_provider_call" and _contains_phi_or_ephi(data_use):
            reasons.append(
                "PHI/ePHI cannot be sent to a model provider without provider-specific approval."
            )
            required_approvals.add("model_provider")

        for source in data_use.sources:
            if data_use.purpose in source.forbidden_uses:
                reasons.append(
                    f"Source {source.source_id!r} forbids use {data_use.purpose!r}."
                )
            if data_use.purpose not in source.allowed_uses:
                reasons.append(
                    f"Source {source.source_id!r} is not approved for use {data_use.purpose!r}."
                )

        approvals = {
            approval.approval_type
            for approval in data_use.approvals
            if approval.complete
        }
        missing_approvals = tuple(sorted(required_approvals - approvals))
        if reasons and missing_approvals:
            return PrivacyGateDecision(
                status=PrivacyReviewStatus.BLOCKED,
                reasons=tuple(reasons),
                missing_approvals=missing_approvals,
            )
        if reasons and not required_approvals:
            return PrivacyGateDecision(
                status=PrivacyReviewStatus.BLOCKED,
                reasons=tuple(reasons),
            )
        return PrivacyGateDecision(status=PrivacyReviewStatus.APPROVED)


def _contains_phi_or_ephi(data_use: WorkflowDataUse) -> bool:
    if data_use.data_classification in {DataClassification.PHI, DataClassification.EPHI}:
        return True
    for source in data_use.sources:
        if source.source_type == "patient_data":
            return True
        if source.phi_pii_status.lower() in {"phi", "ephi"}:
            return True
    return False


__all__ = [
    "DataClassification",
    "PrivacyApproval",
    "PrivacyGate",
    "PrivacyGateDecision",
    "PrivacyReviewStatus",
    "WorkflowDataUse",
]

from src.vyu.privacy.workflow import PrivacyApprovalResult, evaluate_privacy_workflow

__all__.extend(
    [
        "PrivacyApprovalResult",
        "evaluate_privacy_workflow",
    ]
)
