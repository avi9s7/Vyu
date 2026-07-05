from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from src.vyu.authz import AuthorizationPolicy, Principal, Role, WorkspaceMembership
from src.vyu.entrypoints.review_queue import (
    ReviewQueueApiResponse,
    ReviewQueueDecisionApiRequest,
    ReviewQueueDecisionPayload,
    ReviewQueueListApiRequest,
    ReviewQueueListPayload,
    handle_review_queue_decision_api,
    handle_review_queue_list_api,
)
from src.vyu.review import ReviewDecision, ReviewStatus
from src.vyu.storage import ProductionStorage


@dataclass(frozen=True)
class ReviewQueueRouteRequest:
    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)
    query: dict[str, str] = field(default_factory=dict)
    json_body: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ReviewQueueRouteResponse:
    status_code: int
    body: dict[str, object]


class ReviewQueueRouteRuntime:
    def __init__(
        self,
        storage: ProductionStorage,
        policy: AuthorizationPolicy | None = None,
        audit_event_id_factory: Callable[[str, str], str] | None = None,
        audit_created_at: str | None = None,
    ) -> None:
        self.storage = storage
        self.policy = policy
        self.audit_event_id_factory = audit_event_id_factory
        self.audit_created_at = audit_created_at

    def handle(self, request: ReviewQueueRouteRequest) -> ReviewQueueRouteResponse:
        method = request.method.upper()
        try:
            if method == "GET" and request.path == "/v1/review-queue":
                return _from_api_response(self._handle_list(request))
            if method == "POST" and _is_decision_route(request.path):
                return _from_api_response(self._handle_decision(request))
        except (KeyError, ValueError) as exc:
            return ReviewQueueRouteResponse(
                status_code=400,
                body={
                    "reason": "route_bad_request",
                    "detail": str(exc),
                    "method": method,
                    "path": request.path,
                },
            )
        return ReviewQueueRouteResponse(
            status_code=404,
            body={
                "reason": "route_not_found",
                "method": method,
                "path": request.path,
            },
        )

    def _handle_list(
        self,
        request: ReviewQueueRouteRequest,
    ) -> ReviewQueueApiResponse:
        return handle_review_queue_list_api(
            ReviewQueueListApiRequest(
                request_id=_request_id(request),
                payload=ReviewQueueListPayload(
                    principal=_principal_from_headers(request.headers),
                    tenant_id=str(request.query["tenant_id"]),
                    workspace_id=str(request.query["workspace_id"]),
                    status=(
                        ReviewStatus(str(request.query["status"]))
                        if request.query.get("status")
                        else None
                    ),
                    run_id=request.query.get("run_id"),
                ),
            ),
            storage=self.storage,
            policy=self.policy,
        )

    def _handle_decision(
        self,
        request: ReviewQueueRouteRequest,
    ) -> ReviewQueueApiResponse:
        return handle_review_queue_decision_api(
            ReviewQueueDecisionApiRequest(
                request_id=_request_id(request),
                payload=ReviewQueueDecisionPayload(
                    principal=_principal_from_headers(request.headers),
                    review_id=_review_id_from_decision_route(request.path),
                    decision=ReviewDecision(str(request.json_body["decision"])),
                    comment=str(request.json_body["comment"]),
                    decided_at=str(request.json_body["decided_at"]),
                ),
            ),
            storage=self.storage,
            policy=self.policy,
            audit_event_id_factory=self.audit_event_id_factory,
            audit_created_at=self.audit_created_at,
        )


def _from_api_response(response: ReviewQueueApiResponse) -> ReviewQueueRouteResponse:
    return ReviewQueueRouteResponse(
        status_code=response.status_code,
        body=response.body,
    )


def _principal_from_headers(headers: dict[str, str]) -> Principal:
    return Principal(
        user_id=str(headers["x-vyu-user-id"]),
        memberships=(
            WorkspaceMembership(
                tenant_id=str(headers["x-vyu-tenant-id"]),
                workspace_id=str(headers["x-vyu-workspace-id"]),
                roles=(Role(str(headers["x-vyu-role"])),),
            ),
        ),
    )


def _request_id(request: ReviewQueueRouteRequest) -> str:
    return request.headers.get("x-vyu-request-id", "review-queue-route")


def _is_decision_route(path: str) -> bool:
    parts = path.strip("/").split("/")
    return len(parts) == 4 and parts[0] == "v1" and parts[1] == "review-queue" and parts[3] == "decision"


def _review_id_from_decision_route(path: str) -> str:
    return path.strip("/").split("/")[2]
