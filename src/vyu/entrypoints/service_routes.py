from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping, Protocol

from src.vyu.authn import IdentityMapper, IdentityMappingDecision, IdentityMappingError
from src.vyu.authz import Role
from src.vyu.entrypoints.report_export_routes import (
    ReportExportRouteRequest,
    ReportExportRouteRuntime,
)
from src.vyu.entrypoints.review_queue_routes import (
    ReviewQueueRouteRequest,
    ReviewQueueRouteRuntime,
)
from src.vyu.entrypoints.tenant_governance_admin_routes import (
    TenantGovernanceAdminRouteRequest,
    TenantGovernanceAdminRouteRuntime,
)


@dataclass(frozen=True)
class ServiceRouteRequest:
    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)
    query: dict[str, str] = field(default_factory=dict)
    json_body: dict[str, object] = field(default_factory=dict)
    identity_claims: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ServiceRouteResponse:
    status_code: int
    body: dict[str, object]
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedServiceRouteRequest:
    request: ServiceRouteRequest
    identity_decision: IdentityMappingDecision | None = None


class ServiceRouteHandler(Protocol):
    def handle(self, request: ServiceRouteRequest) -> ServiceRouteResponse:
        ...


class ServiceRouteRuntime:
    """Framework-neutral top-level route runtime for deployed-service wiring."""

    def __init__(
        self,
        review_queue_runtime: ReviewQueueRouteRuntime,
        report_export_runtime: ReportExportRouteRuntime,
        request_id_factory: Callable[[], str] | None = None,
        identity_mapper: IdentityMapper | None = None,
        tenant_governance_admin_runtime: TenantGovernanceAdminRouteRuntime | None = None,
        identity_audit_sink: Callable[[Mapping[str, object]], None] | None = None,
    ) -> None:
        self.review_queue_runtime = review_queue_runtime
        self.report_export_runtime = report_export_runtime
        self.request_id_factory = request_id_factory or (lambda: "service-route")
        self.identity_mapper = identity_mapper
        self.tenant_governance_admin_runtime = tenant_governance_admin_runtime
        self.identity_audit_sink = identity_audit_sink

    def handle(self, request: ServiceRouteRequest) -> ServiceRouteResponse:
        try:
            normalized_result = _normalize_request(
                request,
                self.request_id_factory,
                self.identity_mapper,
            )
        except IdentityMappingError as exc:
            request_id = _request_id_from_headers(request.headers, self.request_id_factory)
            audit_correlation_id = _audit_correlation_id_from_headers(request.headers, request_id)
            self._audit_identity(
                allowed=False,
                reason="identity_mapping_failed",
                detail=str(exc),
                request_id=request_id,
                audit_correlation_id=audit_correlation_id,
                method=request.method.upper(),
                path=request.path,
                decision=None,
            )
            return _service_error(
                status_code=401,
                request_id=request_id,
                audit_correlation_id=audit_correlation_id,
                reason="identity_mapping_failed",
                detail=str(exc),
                method=request.method.upper(),
                path=request.path,
            )
        normalized = normalized_result.request
        request_id = normalized.headers["x-vyu-request-id"]
        audit_correlation_id = normalized.headers["x-vyu-audit-correlation-id"]
        method = normalized.method.upper()
        self._audit_identity(
            allowed=True,
            reason="identity_mapping_succeeded",
            detail="Identity mapped and governed.",
            request_id=request_id,
            audit_correlation_id=audit_correlation_id,
            method=method,
            path=normalized.path,
            decision=normalized_result.identity_decision,
        )

        if method == "GET" and normalized.path == "/v1/health":
            return _service_response(
                status_code=200,
                request_id=request_id,
                audit_correlation_id=audit_correlation_id,
                data={"reason": "service_healthy"},
                reason="service_healthy",
            )

        route_family = _route_family(normalized.path)
        if route_family is None:
            return _service_error(
                status_code=404,
                request_id=request_id,
                audit_correlation_id=audit_correlation_id,
                reason="route_not_found",
                detail=f"No service route registered for {method} {normalized.path}.",
                method=method,
                path=normalized.path,
            )

        identity_error = _identity_error(normalized.headers)
        if identity_error is not None:
            return _service_error(
                status_code=401,
                request_id=request_id,
                audit_correlation_id=audit_correlation_id,
                reason="identity_required",
                detail=identity_error,
                method=method,
                path=normalized.path,
            )

        if route_family == "review_queue":
            route_response = self.review_queue_runtime.handle(
                ReviewQueueRouteRequest(
                    method=method,
                    path=normalized.path,
                    headers=normalized.headers,
                    query=normalized.query,
                    json_body=normalized.json_body,
                )
            )
        elif route_family == "report_export":
            route_response = self.report_export_runtime.handle(
                ReportExportRouteRequest(
                    method=method,
                    path=normalized.path,
                    headers=normalized.headers,
                    query=normalized.query,
                    json_body=normalized.json_body,
                )
            )
        else:
            if self.tenant_governance_admin_runtime is None:
                return _service_error(
                    status_code=503,
                    request_id=request_id,
                    audit_correlation_id=audit_correlation_id,
                    reason="tenant_governance_admin_unavailable",
                    detail="Tenant governance admin runtime is not configured.",
                    method=method,
                    path=normalized.path,
                )
            route_response = self.tenant_governance_admin_runtime.handle(
                TenantGovernanceAdminRouteRequest(
                    method=method,
                    path=normalized.path,
                    headers=normalized.headers,
                    query=normalized.query,
                    json_body=normalized.json_body,
                )
            )

        return _service_response(
            status_code=route_response.status_code,
            request_id=request_id,
            audit_correlation_id=audit_correlation_id,
            data=dict(route_response.body),
            reason=str(route_response.body.get("reason", _status_reason(route_response.status_code))),
        )

    def _audit_identity(
        self,
        *,
        allowed: bool,
        reason: str,
        detail: str,
        request_id: str,
        audit_correlation_id: str,
        method: str,
        path: str,
        decision: IdentityMappingDecision | None,
    ) -> None:
        if self.identity_audit_sink is None or (decision is None and allowed):
            return
        identity_payload: dict[str, object] | None = None
        if decision is not None:
            identity = decision.mapped_identity
            identity_payload = {
                "user_id": identity.user_id,
                "tenant_id": identity.tenant_id,
                "workspace_id": identity.workspace_id,
                "role": identity.role.value,
                "issuer": identity.issuer,
                "audience": list(identity.audience),
                "governed_grant_ids": list(identity.governed_grant_ids),
                "governed_access_modes": list(identity.governed_access_modes),
                "break_glass_used": bool(identity.break_glass_reason),
                "mapped_role_claims": list(decision.mapped_role_claims),
                "ignored_role_claims": list(decision.ignored_role_claims),
            }
        self.identity_audit_sink(
            {
                "event_type": "identity_access_decision",
                "allowed": allowed,
                "reason": reason,
                "detail": detail,
                "request_id": request_id,
                "audit_correlation_id": audit_correlation_id,
                "method": method,
                "path": path,
                "identity": identity_payload,
            }
        )


def _normalize_request(
    request: ServiceRouteRequest,
    request_id_factory: Callable[[], str],
    identity_mapper: IdentityMapper | None,
) -> NormalizedServiceRouteRequest:
    headers = {str(key).lower(): str(value) for key, value in request.headers.items()}
    identity_decision: IdentityMappingDecision | None = None
    if identity_mapper is not None and request.identity_claims:
        identity_decision = identity_mapper.map_claims(request.identity_claims)
        headers.update(identity_decision.to_service_headers())
    request_id = headers.get("x-vyu-request-id") or request_id_factory()
    headers["x-vyu-request-id"] = request_id
    headers.setdefault("x-vyu-audit-correlation-id", request_id)
    normalized = ServiceRouteRequest(
        method=request.method.upper(),
        path=request.path,
        headers=headers,
        query={str(key): str(value) for key, value in request.query.items()},
        json_body=dict(request.json_body),
        identity_claims=dict(request.identity_claims),
    )
    return NormalizedServiceRouteRequest(
        request=normalized,
        identity_decision=identity_decision,
    )


def _request_id_from_headers(
    headers: dict[str, str],
    request_id_factory: Callable[[], str],
) -> str:
    normalized = {str(key).lower(): str(value) for key, value in headers.items()}
    return normalized.get("x-vyu-request-id") or request_id_factory()


def _audit_correlation_id_from_headers(headers: dict[str, str], request_id: str) -> str:
    normalized = {str(key).lower(): str(value) for key, value in headers.items()}
    return normalized.get("x-vyu-audit-correlation-id") or request_id


def _route_family(path: str) -> str | None:
    if path == "/v1/review-queue" or path.startswith("/v1/review-queue/"):
        return "review_queue"
    if path == "/v1/report-exports":
        return "report_export"
    if path == "/v1/admin/tenant-governance" or path.startswith("/v1/admin/"):
        return "tenant_governance_admin"
    return None


def _identity_error(headers: dict[str, str]) -> str | None:
    required = (
        "x-vyu-user-id",
        "x-vyu-tenant-id",
        "x-vyu-workspace-id",
        "x-vyu-role",
    )
    missing = [header for header in required if not headers.get(header)]
    if missing:
        return f"Missing required identity headers: {', '.join(missing)}."
    try:
        Role(headers["x-vyu-role"])
    except ValueError:
        return f"Unknown Vyu role: {headers['x-vyu-role']}."
    return None


def _service_response(
    status_code: int,
    request_id: str,
    audit_correlation_id: str,
    data: dict[str, object],
    reason: str,
) -> ServiceRouteResponse:
    status = "ok" if 200 <= status_code < 400 else "error"
    body: dict[str, object] = {
        "request_id": request_id,
        "audit_correlation_id": audit_correlation_id,
        "status": status,
        "reason": reason,
        "data": data,
    }
    if status == "error":
        body["error"] = {
            "reason": reason,
            "detail": str(data.get("detail", reason)),
        }
    return ServiceRouteResponse(
        status_code=status_code,
        body=body,
        headers={
            "x-vyu-request-id": request_id,
            "x-vyu-audit-correlation-id": audit_correlation_id,
        },
    )


def _service_error(
    status_code: int,
    request_id: str,
    audit_correlation_id: str,
    reason: str,
    detail: str,
    method: str,
    path: str,
) -> ServiceRouteResponse:
    return _service_response(
        status_code=status_code,
        request_id=request_id,
        audit_correlation_id=audit_correlation_id,
        reason=reason,
        data={
            "reason": reason,
            "detail": detail,
            "method": method,
            "path": path,
        },
    )


def _status_reason(status_code: int) -> str:
    if status_code == 403:
        return "forbidden"
    if status_code == 404:
        return "route_not_found"
    if status_code >= 400:
        return "route_error"
    return "route_ok"
