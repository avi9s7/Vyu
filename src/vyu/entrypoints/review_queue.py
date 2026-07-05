from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.vyu.authz import AuthorizationPolicy, Principal
from src.vyu.review import (
    ReviewDecision,
    ReviewStatus,
    decide_queued_review_task,
    list_review_queue,
)
from src.vyu.storage import ProductionScope, ProductionStorage


@dataclass(frozen=True)
class ReviewQueueListPayload:
    principal: Principal
    tenant_id: str
    workspace_id: str
    status: ReviewStatus | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class ReviewQueueDecisionPayload:
    principal: Principal
    review_id: str
    decision: ReviewDecision
    comment: str
    decided_at: str


@dataclass(frozen=True)
class ReviewQueueListApiRequest:
    request_id: str
    payload: ReviewQueueListPayload


@dataclass(frozen=True)
class ReviewQueueDecisionApiRequest:
    request_id: str
    payload: ReviewQueueDecisionPayload


@dataclass(frozen=True)
class ReviewQueueApiResponse:
    status_code: int
    body: dict[str, object]


@dataclass(frozen=True)
class ReviewQueueListWorkerJob:
    job_id: str
    payload: ReviewQueueListPayload


@dataclass(frozen=True)
class ReviewQueueDecisionWorkerJob:
    job_id: str
    payload: ReviewQueueDecisionPayload


@dataclass(frozen=True)
class ReviewQueueWorkerResult:
    job_id: str
    status: str
    review_tasks: tuple[dict[str, object], ...] = ()
    review_task: dict[str, object] | None = None
    reason: str = ""

    def to_json(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "review_tasks": [dict(task) for task in self.review_tasks],
            "review_task": dict(self.review_task) if self.review_task else None,
            "reason": self.reason,
        }


def handle_review_queue_list_api(
    request: ReviewQueueListApiRequest,
    storage: ProductionStorage,
    policy: AuthorizationPolicy | None = None,
) -> ReviewQueueApiResponse:
    try:
        tasks = _list_tasks(request.payload, storage, policy)
    except PermissionError:
        return ReviewQueueApiResponse(
            status_code=403,
            body={
                "request_id": request.request_id,
                "tenant_id": request.payload.tenant_id,
                "workspace_id": request.payload.workspace_id,
                "reason": "review_queue_not_authorized",
                "review_tasks": [],
            },
        )
    return ReviewQueueApiResponse(
        status_code=200,
        body={
            "request_id": request.request_id,
            "tenant_id": request.payload.tenant_id,
            "workspace_id": request.payload.workspace_id,
            "reason": "review_queue_loaded",
            "review_tasks": [task.to_json() for task in tasks],
        },
    )


def handle_review_queue_decision_api(
    request: ReviewQueueDecisionApiRequest,
    storage: ProductionStorage,
    policy: AuthorizationPolicy | None = None,
    audit_event_id_factory: Callable[[str, str], str] | None = None,
    audit_created_at: str | None = None,
) -> ReviewQueueApiResponse:
    try:
        task = _decide_task(
            payload=request.payload,
            storage=storage,
            policy=policy,
            audit_event_id_factory=audit_event_id_factory,
            audit_created_at=audit_created_at,
        )
    except PermissionError:
        return ReviewQueueApiResponse(
            status_code=403,
            body={
                "request_id": request.request_id,
                "reason": "review_decision_not_authorized",
                "review_task": None,
            },
        )
    return ReviewQueueApiResponse(
        status_code=200,
        body={
            "request_id": request.request_id,
            "reason": "review_decision_recorded",
            "review_task": task.to_json(),
        },
    )


def run_review_queue_list_worker_job(
    job: ReviewQueueListWorkerJob,
    storage: ProductionStorage,
    policy: AuthorizationPolicy | None = None,
) -> ReviewQueueWorkerResult:
    try:
        tasks = _list_tasks(job.payload, storage, policy)
    except PermissionError:
        return ReviewQueueWorkerResult(
            job_id=job.job_id,
            status="blocked",
            reason="review_queue_not_authorized",
        )
    return ReviewQueueWorkerResult(
        job_id=job.job_id,
        status="completed",
        review_tasks=tuple(task.to_json() for task in tasks),
        reason="review_queue_loaded",
    )


def run_review_queue_decision_worker_job(
    job: ReviewQueueDecisionWorkerJob,
    storage: ProductionStorage,
    policy: AuthorizationPolicy | None = None,
    audit_event_id_factory: Callable[[str, str], str] | None = None,
    audit_created_at: str | None = None,
) -> ReviewQueueWorkerResult:
    try:
        task = _decide_task(
            payload=job.payload,
            storage=storage,
            policy=policy,
            audit_event_id_factory=audit_event_id_factory,
            audit_created_at=audit_created_at,
        )
    except PermissionError:
        return ReviewQueueWorkerResult(
            job_id=job.job_id,
            status="blocked",
            reason="review_decision_not_authorized",
        )
    return ReviewQueueWorkerResult(
        job_id=job.job_id,
        status="completed",
        review_task=task.to_json(),
        reason="review_decision_recorded",
    )


def _list_tasks(
    payload: ReviewQueueListPayload,
    storage: ProductionStorage,
    policy: AuthorizationPolicy | None,
):
    return list_review_queue(
        storage=storage,
        principal=payload.principal,
        scope=ProductionScope(
            tenant_id=payload.tenant_id,
            workspace_id=payload.workspace_id,
        ),
        status=payload.status,
        run_id=payload.run_id,
        policy=policy,
    )


def _decide_task(
    payload: ReviewQueueDecisionPayload,
    storage: ProductionStorage,
    policy: AuthorizationPolicy | None,
    audit_event_id_factory: Callable[[str, str], str] | None,
    audit_created_at: str | None,
):
    task = storage.get_review_task(payload.review_id)
    event_type = "review_decision_recorded"
    return decide_queued_review_task(
        storage=storage,
        principal=payload.principal,
        review_id=payload.review_id,
        decision=payload.decision,
        comment=payload.comment,
        decided_at=payload.decided_at,
        audit_event_id=(
            audit_event_id_factory(task.run_id, event_type)
            if audit_event_id_factory is not None
            else f"{task.run_id}-{event_type}-{payload.decided_at}"
        ),
        audit_created_at=audit_created_at or payload.decided_at,
        policy=policy,
    )
