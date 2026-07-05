from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.vyu.authz import AuthorizationPolicy, Principal
from src.vyu.generation import EvidenceContext, GroundedAnswer
from src.vyu.governance import GovernanceBox, TrustScore
from src.vyu.reports import ReportType, export_report
from src.vyu.review import ReviewTask
from src.vyu.storage import ProductionStorage


@dataclass(frozen=True)
class ReportExportPayload:
    principal: Principal
    report_type: ReportType
    answer: GroundedAnswer
    context: EvidenceContext
    trust_score: TrustScore
    governance_box: GovernanceBox
    review_task: ReviewTask


@dataclass(frozen=True)
class ReportExportApiRequest:
    request_id: str
    payload: ReportExportPayload


@dataclass(frozen=True)
class ReportExportApiResponse:
    status_code: int
    body: dict[str, object]


@dataclass(frozen=True)
class ReportExportWorkerJob:
    job_id: str
    payload: ReportExportPayload


@dataclass(frozen=True)
class ReportExportWorkerResult:
    job_id: str
    status: str
    export: dict[str, object]

    def to_json(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "export": dict(self.export),
        }


def handle_report_export_api(
    request: ReportExportApiRequest,
    storage: ProductionStorage | None = None,
    policy: AuthorizationPolicy | None = None,
    audit_event_id_factory: Callable[[str, str], str] | None = None,
    audit_created_at: str | None = None,
) -> ReportExportApiResponse:
    result = _export(
        payload=request.payload,
        storage=storage,
        policy=policy,
        audit_event_id_factory=audit_event_id_factory,
        audit_created_at=audit_created_at,
    )
    body = {
        "request_id": request.request_id,
        "run_id": request.payload.review_task.run_id,
        "tenant_id": request.payload.review_task.scope.tenant_id,
        "workspace_id": request.payload.review_task.scope.workspace_id,
        "export": result.to_json(),
    }
    return ReportExportApiResponse(
        status_code=200 if result.allowed else 403,
        body=body,
    )


def run_report_export_worker_job(
    job: ReportExportWorkerJob,
    storage: ProductionStorage | None = None,
    policy: AuthorizationPolicy | None = None,
    audit_event_id_factory: Callable[[str, str], str] | None = None,
    audit_created_at: str | None = None,
) -> ReportExportWorkerResult:
    result = _export(
        payload=job.payload,
        storage=storage,
        policy=policy,
        audit_event_id_factory=audit_event_id_factory,
        audit_created_at=audit_created_at,
    )
    return ReportExportWorkerResult(
        job_id=job.job_id,
        status="completed" if result.allowed else "blocked",
        export=result.to_json(),
    )


def _export(
    payload: ReportExportPayload,
    storage: ProductionStorage | None,
    policy: AuthorizationPolicy | None,
    audit_event_id_factory: Callable[[str, str], str] | None,
    audit_created_at: str | None,
):
    return export_report(
        principal=payload.principal,
        report_type=payload.report_type,
        answer=payload.answer,
        context=payload.context,
        trust_score=payload.trust_score,
        governance_box=payload.governance_box,
        review_task=payload.review_task,
        policy=policy,
        storage=storage,
        audit_event_id_factory=audit_event_id_factory,
        audit_created_at=audit_created_at,
    )
