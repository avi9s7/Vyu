from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.vyu.privacy import (
    DataClassification,
    PrivacyApproval,
    WorkflowDataUse,
)
from src.vyu.privacy.workflow import (
    PrivacyApprovalResult,
    evaluate_privacy_workflow,
)
from src.vyu.sources import ProductionSourceRecord
from src.vyu.storage import ProductionStorage


@dataclass(frozen=True)
class PrivacyApprovalPayload:
    run_id: str
    tenant_id: str
    workspace_id: str
    purpose: str
    data_classification: DataClassification
    sources: tuple[ProductionSourceRecord, ...] = ()
    approvals: tuple[PrivacyApproval, ...] = ()


@dataclass(frozen=True)
class PrivacyApprovalApiRequest:
    request_id: str
    payload: PrivacyApprovalPayload


@dataclass(frozen=True)
class PrivacyApprovalApiResponse:
    status_code: int
    body: dict[str, object]


@dataclass(frozen=True)
class PrivacyApprovalWorkerJob:
    job_id: str
    payload: PrivacyApprovalPayload


@dataclass(frozen=True)
class PrivacyApprovalWorkerResult:
    job_id: str
    status: str
    privacy: dict[str, object]

    def to_json(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "privacy": dict(self.privacy),
        }


def handle_privacy_approval_api(
    request: PrivacyApprovalApiRequest,
    storage: ProductionStorage | None = None,
    approval_id_factory: Callable[[str], str] | None = None,
    audit_event_id_factory: Callable[[str, str], str] | None = None,
    evaluated_at: str | None = None,
) -> PrivacyApprovalApiResponse:
    result = _evaluate(
        payload=request.payload,
        storage=storage,
        approval_id_factory=approval_id_factory,
        audit_event_id_factory=audit_event_id_factory,
        evaluated_at=evaluated_at,
    )
    body = {
        "request_id": request.request_id,
        "run_id": request.payload.run_id,
        "tenant_id": request.payload.tenant_id,
        "workspace_id": request.payload.workspace_id,
        "privacy": result.to_json(),
    }
    return PrivacyApprovalApiResponse(
        status_code=200 if result.allowed else 403,
        body=body,
    )


def run_privacy_approval_worker_job(
    job: PrivacyApprovalWorkerJob,
    storage: ProductionStorage | None = None,
    approval_id_factory: Callable[[str], str] | None = None,
    audit_event_id_factory: Callable[[str, str], str] | None = None,
    evaluated_at: str | None = None,
) -> PrivacyApprovalWorkerResult:
    result = _evaluate(
        payload=job.payload,
        storage=storage,
        approval_id_factory=approval_id_factory,
        audit_event_id_factory=audit_event_id_factory,
        evaluated_at=evaluated_at,
    )
    return PrivacyApprovalWorkerResult(
        job_id=job.job_id,
        status="completed" if result.allowed else "blocked",
        privacy=result.to_json(),
    )


def _evaluate(
    payload: PrivacyApprovalPayload,
    storage: ProductionStorage | None,
    approval_id_factory: Callable[[str], str] | None,
    audit_event_id_factory: Callable[[str, str], str] | None,
    evaluated_at: str | None,
) -> PrivacyApprovalResult:
    return evaluate_privacy_workflow(
        run_id=payload.run_id,
        tenant_id=payload.tenant_id,
        workspace_id=payload.workspace_id,
        data_use=WorkflowDataUse(
            purpose=payload.purpose,
            data_classification=payload.data_classification,
            sources=payload.sources,
            approvals=payload.approvals,
        ),
        storage=storage,
        approval_id_factory=approval_id_factory,
        audit_event_id_factory=audit_event_id_factory,
        evaluated_at=evaluated_at,
    )
