from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Mapping

from src.vyu.authz import (
    AccessMode,
    Action,
    ApiKeyRecord,
    ApiKeyStatus,
    AuthorizationPolicy,
    MembershipGrant,
    MembershipGrantStatus,
    Principal,
    ResourceScope,
    Role,
    ServiceAccountRecord,
    ServiceAccountStatus,
    TenantGovernanceRepository,
    TenantRecord,
    TenantStatus,
    WorkspaceMembership,
    WorkspaceRecord,
    WorkspaceStatus,
    hash_api_key_secret,
)


@dataclass(frozen=True)
class TenantGovernanceAdminRouteRequest:
    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)
    query: dict[str, str] = field(default_factory=dict)
    json_body: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class TenantGovernanceAdminRouteResponse:
    status_code: int
    body: dict[str, object]


class TenantGovernanceAdminRouteRuntime:
    """Tenant-admin lifecycle routes for production-operated governance records."""

    def __init__(
        self,
        repository: TenantGovernanceRepository,
        authorization_policy: AuthorizationPolicy | None = None,
        audit_sink: Callable[[Mapping[str, object]], None] | None = None,
    ) -> None:
        self.repository = repository
        self.authorization_policy = authorization_policy or AuthorizationPolicy()
        self.audit_sink = audit_sink

    def handle(
        self,
        request: TenantGovernanceAdminRouteRequest,
    ) -> TenantGovernanceAdminRouteResponse:
        method = request.method.upper()
        headers = {str(key).lower(): str(value) for key, value in request.headers.items()}
        try:
            self._require_tenant_admin(headers)
        except PermissionError as exc:
            return _response(403, "tenant_admin_required", detail=str(exc))

        segments = _path_segments(request.path)
        try:
            if method == "GET" and segments == ["v1", "admin", "tenant-governance"]:
                return _response(
                    200,
                    "tenant_governance_loaded",
                    registry=self.repository.read().to_safe_json(),
                )
            if len(segments) == 4 and segments[:3] == ["v1", "admin", "tenants"]:
                if method == "PUT":
                    return self._upsert_tenant(segments[3], request, headers)
            if len(segments) == 4 and segments[:3] == ["v1", "admin", "workspaces"]:
                if method == "PUT":
                    return self._upsert_workspace(segments[3], request, headers)
            if len(segments) == 4 and segments[:3] == ["v1", "admin", "membership-grants"]:
                if method == "PUT":
                    return self._upsert_membership_grant(segments[3], request, headers)
            if len(segments) == 5 and segments[:3] == ["v1", "admin", "membership-grants"]:
                if method == "POST" and segments[4] == "revoke":
                    return self._revoke_membership_grant(segments[3], request, headers)
            if len(segments) == 4 and segments[:3] == ["v1", "admin", "service-accounts"]:
                if method == "PUT":
                    return self._upsert_service_account(segments[3], request, headers)
            if len(segments) == 4 and segments[:3] == ["v1", "admin", "api-keys"]:
                if method == "PUT":
                    return self._upsert_api_key(segments[3], request, headers)
        except (KeyError, TypeError, ValueError) as exc:
            return _response(400, "tenant_governance_admin_invalid_request", detail=str(exc))

        return _response(
            404,
            "tenant_governance_admin_route_not_found",
            detail=f"No tenant-governance admin route registered for {method} {request.path}.",
        )

    def _require_tenant_admin(self, headers: Mapping[str, str]) -> None:
        role = Role(str(headers.get("x-vyu-role", "")))
        tenant_id = str(headers.get("x-vyu-tenant-id", ""))
        workspace_id = str(headers.get("x-vyu-workspace-id", "")) or "*"
        principal = Principal(
            user_id=str(headers.get("x-vyu-user-id", "")),
            memberships=(
                WorkspaceMembership(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    roles=(role,),
                ),
            ),
        )
        self.authorization_policy.require(
            principal,
            Action.MANAGE_TENANT,
            ResourceScope(tenant_id=tenant_id, workspace_id=workspace_id),
        )

    def _upsert_tenant(
        self,
        tenant_id: str,
        request: TenantGovernanceAdminRouteRequest,
        headers: Mapping[str, str],
    ) -> TenantGovernanceAdminRouteResponse:
        body = request.json_body
        tenant = TenantRecord(
            tenant_id=tenant_id,
            display_name=str(body.get("display_name", tenant_id)),
            status=TenantStatus(str(body.get("status", TenantStatus.ACTIVE.value))),
            allowed_email_domains=tuple(str(item) for item in body.get("allowed_email_domains", [])),
            created_at=str(body.get("created_at", _now_iso())),
            metadata=_metadata(body),
        )
        self.repository.upsert_tenant(tenant)
        self._audit(headers, "upsert_tenant", {"tenant_id": tenant_id})
        return _response(200, "tenant_upserted", tenant=tenant.to_json())

    def _upsert_workspace(
        self,
        workspace_id: str,
        request: TenantGovernanceAdminRouteRequest,
        headers: Mapping[str, str],
    ) -> TenantGovernanceAdminRouteResponse:
        body = request.json_body
        tenant_id = str(body.get("tenant_id", headers.get("x-vyu-tenant-id", ""))).strip()
        if not tenant_id:
            raise ValueError("tenant_id is required.")
        workspace = WorkspaceRecord(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            display_name=str(body.get("display_name", workspace_id)),
            status=WorkspaceStatus(str(body.get("status", WorkspaceStatus.ACTIVE.value))),
            data_classification=str(body.get("data_classification", "public_literature")),
            created_at=str(body.get("created_at", _now_iso())),
            metadata=_metadata(body),
        )
        self.repository.upsert_workspace(workspace)
        self._audit(headers, "upsert_workspace", {"tenant_id": tenant_id, "workspace_id": workspace_id})
        return _response(200, "workspace_upserted", workspace=workspace.to_json())

    def _upsert_membership_grant(
        self,
        grant_id: str,
        request: TenantGovernanceAdminRouteRequest,
        headers: Mapping[str, str],
    ) -> TenantGovernanceAdminRouteResponse:
        body = request.json_body
        tenant_id = str(body.get("tenant_id", headers.get("x-vyu-tenant-id", ""))).strip()
        workspace_id = str(body.get("workspace_id", "")).strip()
        user_id = str(body.get("user_id", "")).strip()
        if not tenant_id or not workspace_id or not user_id:
            raise ValueError("tenant_id, workspace_id, and user_id are required.")
        grant = MembershipGrant(
            grant_id=grant_id,
            user_id=user_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            roles=_roles(body.get("roles", [])),
            status=MembershipGrantStatus(str(body.get("status", MembershipGrantStatus.ACTIVE.value))),
            access_mode=AccessMode(str(body.get("access_mode", AccessMode.STANDARD.value))),
            granted_by=str(body.get("granted_by", headers.get("x-vyu-user-id", ""))),
            granted_at=str(body.get("granted_at", _now_iso())),
            expires_at=(str(body["expires_at"]) if body.get("expires_at") is not None else None),
            reason=str(body.get("reason", "")),
            metadata=_metadata(body),
        )
        if not grant.roles:
            raise ValueError("At least one role is required.")
        self.repository.upsert_membership_grant(grant)
        self._audit(headers, "upsert_membership_grant", {"grant_id": grant_id, "tenant_id": tenant_id, "workspace_id": workspace_id, "user_id": user_id})
        return _response(200, "membership_grant_upserted", membership_grant=grant.to_json())

    def _revoke_membership_grant(
        self,
        grant_id: str,
        request: TenantGovernanceAdminRouteRequest,
        headers: Mapping[str, str],
    ) -> TenantGovernanceAdminRouteResponse:
        revoked_at = str(request.json_body.get("revoked_at", _now_iso()))
        registry = self.repository.revoke_membership_grant(
            grant_id,
            revoked_by=str(headers.get("x-vyu-user-id", "")),
            revoked_at=revoked_at,
        )
        grant = next(item for item in registry.membership_grants if item.grant_id == grant_id)
        self._audit(headers, "revoke_membership_grant", {"grant_id": grant_id})
        return _response(200, "membership_grant_revoked", membership_grant=grant.to_json())

    def _upsert_service_account(
        self,
        service_account_id: str,
        request: TenantGovernanceAdminRouteRequest,
        headers: Mapping[str, str],
    ) -> TenantGovernanceAdminRouteResponse:
        body = request.json_body
        tenant_id = str(body.get("tenant_id", headers.get("x-vyu-tenant-id", ""))).strip()
        if not tenant_id:
            raise ValueError("tenant_id is required.")
        account = ServiceAccountRecord(
            service_account_id=service_account_id,
            tenant_id=tenant_id,
            display_name=str(body.get("display_name", service_account_id)),
            status=ServiceAccountStatus(str(body.get("status", ServiceAccountStatus.ACTIVE.value))),
            allowed_scopes=tuple(str(item) for item in body.get("allowed_scopes", [])),
            created_at=str(body.get("created_at", _now_iso())),
            created_by=str(body.get("created_by", headers.get("x-vyu-user-id", ""))),
            metadata=_metadata(body),
        )
        self.repository.upsert_service_account(account)
        self._audit(headers, "upsert_service_account", {"service_account_id": service_account_id, "tenant_id": tenant_id})
        return _response(200, "service_account_upserted", service_account=account.to_json())

    def _upsert_api_key(
        self,
        key_id: str,
        request: TenantGovernanceAdminRouteRequest,
        headers: Mapping[str, str],
    ) -> TenantGovernanceAdminRouteResponse:
        body = request.json_body
        secret_hash = str(body.get("secret_hash", "")).strip()
        if body.get("secret"):
            secret_hash = hash_api_key_secret(str(body["secret"]))
        if not secret_hash.startswith("sha256:"):
            raise ValueError("secret or sha256 secret_hash is required.")
        tenant_id = str(body.get("tenant_id", headers.get("x-vyu-tenant-id", ""))).strip()
        workspace_id = str(body.get("workspace_id", "")).strip()
        service_account_id = str(body.get("service_account_id", "")).strip()
        if not tenant_id or not workspace_id or not service_account_id:
            raise ValueError("tenant_id, workspace_id, and service_account_id are required.")
        api_key = ApiKeyRecord(
            key_id=key_id,
            service_account_id=service_account_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            roles=_roles(body.get("roles", [])),
            secret_hash=secret_hash,
            status=ApiKeyStatus(str(body.get("status", ApiKeyStatus.ACTIVE.value))),
            allowed_scopes=tuple(str(item) for item in body.get("allowed_scopes", [])),
            created_at=str(body.get("created_at", _now_iso())),
            created_by=str(body.get("created_by", headers.get("x-vyu-user-id", ""))),
            expires_at=(str(body["expires_at"]) if body.get("expires_at") is not None else None),
            last_rotated_at=str(body.get("last_rotated_at", _now_iso())),
            metadata=_metadata(body),
        )
        if not api_key.roles:
            raise ValueError("At least one role is required.")
        self.repository.upsert_api_key(api_key)
        self._audit(headers, "upsert_api_key", {"key_id": key_id, "tenant_id": tenant_id, "workspace_id": workspace_id, "service_account_id": service_account_id})
        return _response(
            200,
            "api_key_upserted",
            api_key=api_key.to_json(redact_secret_hash=True),
        )

    def _audit(
        self,
        headers: Mapping[str, str],
        action: str,
        payload: Mapping[str, object],
    ) -> None:
        if self.audit_sink is None:
            return
        self.audit_sink(
            {
                "event_type": "tenant_governance_admin_action",
                "action": action,
                "admin_user_id": str(headers.get("x-vyu-user-id", "")),
                "tenant_id": str(headers.get("x-vyu-tenant-id", "")),
                "workspace_id": str(headers.get("x-vyu-workspace-id", "")),
                "payload": dict(payload),
            }
        )


def _response(status_code: int, reason: str, **fields: object) -> TenantGovernanceAdminRouteResponse:
    body: dict[str, object] = {"reason": reason}
    body.update(fields)
    return TenantGovernanceAdminRouteResponse(status_code=status_code, body=body)


def _path_segments(path: str) -> list[str]:
    return [segment for segment in path.strip("/").split("/") if segment]


def _roles(value: object) -> tuple[Role, ...]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = []
    return tuple(Role(str(item)) for item in values if str(item).strip())


def _metadata(body: Mapping[str, object]) -> dict[str, str]:
    metadata = body.get("metadata", {})
    if not isinstance(metadata, Mapping):
        return {}
    return {str(key): str(value) for key, value in metadata.items()}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
