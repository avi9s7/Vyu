from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable, Mapping

from src.vyu.authz import Principal, Role, WorkspaceMembership


class TenantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class WorkspaceStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class MembershipGrantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class ServiceAccountStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class ApiKeyStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class AccessMode(StrEnum):
    STANDARD = "standard"
    BREAK_GLASS = "break_glass"


@dataclass(frozen=True)
class TenantRecord:
    tenant_id: str
    display_name: str
    status: TenantStatus = TenantStatus.ACTIVE
    allowed_email_domains: tuple[str, ...] = ()
    created_at: str = ""
    metadata: Mapping[str, str] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "display_name": self.display_name,
            "status": self.status.value,
            "allowed_email_domains": list(self.allowed_email_domains),
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "TenantRecord":
        return cls(
            tenant_id=str(payload["tenant_id"]),
            display_name=str(payload.get("display_name", payload["tenant_id"])),
            status=TenantStatus(str(payload.get("status", TenantStatus.ACTIVE.value))),
            allowed_email_domains=tuple(
                _normalize_domain(domain)
                for domain in payload.get("allowed_email_domains", [])
            ),
            created_at=str(payload.get("created_at", "")),
            metadata={str(key): str(value) for key, value in dict(payload.get("metadata", {})).items()},
        )


@dataclass(frozen=True)
class WorkspaceRecord:
    tenant_id: str
    workspace_id: str
    display_name: str
    status: WorkspaceStatus = WorkspaceStatus.ACTIVE
    data_classification: str = "public_literature"
    created_at: str = ""
    metadata: Mapping[str, str] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "display_name": self.display_name,
            "status": self.status.value,
            "data_classification": self.data_classification,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "WorkspaceRecord":
        return cls(
            tenant_id=str(payload["tenant_id"]),
            workspace_id=str(payload["workspace_id"]),
            display_name=str(payload.get("display_name", payload["workspace_id"])),
            status=WorkspaceStatus(str(payload.get("status", WorkspaceStatus.ACTIVE.value))),
            data_classification=str(payload.get("data_classification", "public_literature")),
            created_at=str(payload.get("created_at", "")),
            metadata={str(key): str(value) for key, value in dict(payload.get("metadata", {})).items()},
        )


@dataclass(frozen=True)
class MembershipGrant:
    grant_id: str
    user_id: str
    tenant_id: str
    workspace_id: str
    roles: tuple[Role, ...]
    status: MembershipGrantStatus = MembershipGrantStatus.ACTIVE
    access_mode: AccessMode = AccessMode.STANDARD
    granted_by: str = ""
    granted_at: str = ""
    expires_at: str | None = None
    reason: str = ""
    metadata: Mapping[str, str] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "grant_id": self.grant_id,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "roles": [role.value for role in self.roles],
            "status": self.status.value,
            "access_mode": self.access_mode.value,
            "granted_by": self.granted_by,
            "granted_at": self.granted_at,
            "expires_at": self.expires_at,
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "MembershipGrant":
        return cls(
            grant_id=str(payload["grant_id"]),
            user_id=str(payload["user_id"]),
            tenant_id=str(payload["tenant_id"]),
            workspace_id=str(payload["workspace_id"]),
            roles=tuple(Role(str(role)) for role in payload.get("roles", [])),
            status=MembershipGrantStatus(
                str(payload.get("status", MembershipGrantStatus.ACTIVE.value))
            ),
            access_mode=AccessMode(str(payload.get("access_mode", AccessMode.STANDARD.value))),
            granted_by=str(payload.get("granted_by", "")),
            granted_at=str(payload.get("granted_at", "")),
            expires_at=(
                str(payload["expires_at"])
                if payload.get("expires_at") is not None
                else None
            ),
            reason=str(payload.get("reason", "")),
            metadata={str(key): str(value) for key, value in dict(payload.get("metadata", {})).items()},
        )


@dataclass(frozen=True)
class ServiceAccountRecord:
    service_account_id: str
    tenant_id: str
    display_name: str
    status: ServiceAccountStatus = ServiceAccountStatus.ACTIVE
    allowed_scopes: tuple[str, ...] = ()
    created_at: str = ""
    created_by: str = ""
    metadata: Mapping[str, str] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "service_account_id": self.service_account_id,
            "tenant_id": self.tenant_id,
            "display_name": self.display_name,
            "status": self.status.value,
            "allowed_scopes": list(self.allowed_scopes),
            "created_at": self.created_at,
            "created_by": self.created_by,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "ServiceAccountRecord":
        return cls(
            service_account_id=str(payload["service_account_id"]),
            tenant_id=str(payload["tenant_id"]),
            display_name=str(payload.get("display_name", payload["service_account_id"])),
            status=ServiceAccountStatus(
                str(payload.get("status", ServiceAccountStatus.ACTIVE.value))
            ),
            allowed_scopes=tuple(str(scope) for scope in payload.get("allowed_scopes", [])),
            created_at=str(payload.get("created_at", "")),
            created_by=str(payload.get("created_by", "")),
            metadata={str(key): str(value) for key, value in dict(payload.get("metadata", {})).items()},
        )


@dataclass(frozen=True)
class ApiKeyRecord:
    key_id: str
    service_account_id: str
    tenant_id: str
    workspace_id: str
    roles: tuple[Role, ...]
    secret_hash: str
    status: ApiKeyStatus = ApiKeyStatus.ACTIVE
    allowed_scopes: tuple[str, ...] = ()
    created_at: str = ""
    created_by: str = ""
    expires_at: str | None = None
    last_rotated_at: str = ""
    metadata: Mapping[str, str] = field(default_factory=dict)

    def to_json(self, *, redact_secret_hash: bool = False) -> dict[str, Any]:
        return {
            "key_id": self.key_id,
            "service_account_id": self.service_account_id,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "roles": [role.value for role in self.roles],
            "secret_hash": "<redacted>" if redact_secret_hash else self.secret_hash,
            "status": self.status.value,
            "allowed_scopes": list(self.allowed_scopes),
            "created_at": self.created_at,
            "created_by": self.created_by,
            "expires_at": self.expires_at,
            "last_rotated_at": self.last_rotated_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "ApiKeyRecord":
        secret_hash = str(payload.get("secret_hash", ""))
        if secret_hash == "<redacted>":
            raise ValueError("A redacted API key record cannot be loaded as an active registry.")
        return cls(
            key_id=str(payload["key_id"]),
            service_account_id=str(payload["service_account_id"]),
            tenant_id=str(payload["tenant_id"]),
            workspace_id=str(payload["workspace_id"]),
            roles=tuple(Role(str(role)) for role in payload.get("roles", [])),
            secret_hash=secret_hash,
            status=ApiKeyStatus(str(payload.get("status", ApiKeyStatus.ACTIVE.value))),
            allowed_scopes=tuple(str(scope) for scope in payload.get("allowed_scopes", [])),
            created_at=str(payload.get("created_at", "")),
            created_by=str(payload.get("created_by", "")),
            expires_at=(
                str(payload["expires_at"])
                if payload.get("expires_at") is not None
                else None
            ),
            last_rotated_at=str(payload.get("last_rotated_at", "")),
            metadata={str(key): str(value) for key, value in dict(payload.get("metadata", {})).items()},
        )


@dataclass(frozen=True)
class TenantGovernanceDecision:
    allowed: bool
    reason: str
    principal: Principal | None = None
    effective_roles: tuple[Role, ...] = ()
    matched_grant_ids: tuple[str, ...] = ()
    access_modes: tuple[AccessMode, ...] = ()
    break_glass_reason: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "principal": (
                {
                    "user_id": self.principal.user_id,
                    "memberships": [
                        {
                            "tenant_id": membership.tenant_id,
                            "workspace_id": membership.workspace_id,
                            "roles": [role.value for role in membership.roles],
                        }
                        for membership in self.principal.memberships
                    ],
                }
                if self.principal is not None
                else None
            ),
            "effective_roles": [role.value for role in self.effective_roles],
            "matched_grant_ids": list(self.matched_grant_ids),
            "access_modes": [mode.value for mode in self.access_modes],
            "break_glass_reason": self.break_glass_reason,
        }


@dataclass(frozen=True)
class ApiKeyAuthenticationDecision:
    allowed: bool
    reason: str
    claims: Mapping[str, Any] | None = None
    key_id: str | None = None
    service_account_id: str | None = None


class TenantGovernanceRegistry:
    """Tenant/workspace/membership entitlement registry used after authentication.

    This registry is intentionally dependency-free and provider-neutral. It is a
    governance boundary for local tests, workers, and deployment adapters. A
    deployment can back it with `TenantGovernanceRepository` to keep JSON records
    reloadable and admin-operable without a process restart.
    """

    def __init__(
        self,
        tenants: Iterable[TenantRecord] = (),
        workspaces: Iterable[WorkspaceRecord] = (),
        membership_grants: Iterable[MembershipGrant] = (),
        service_accounts: Iterable[ServiceAccountRecord] = (),
        api_keys: Iterable[ApiKeyRecord] = (),
    ) -> None:
        self._tenants = {tenant.tenant_id: tenant for tenant in tenants}
        self._workspaces = {
            (workspace.tenant_id, workspace.workspace_id): workspace
            for workspace in workspaces
        }
        self._membership_grants = tuple(membership_grants)
        self._service_accounts = {
            account.service_account_id: account for account in service_accounts
        }
        self._api_keys = {key.key_id: key for key in api_keys}

    @property
    def tenants(self) -> tuple[TenantRecord, ...]:
        return tuple(self._tenants[key] for key in sorted(self._tenants))

    @property
    def workspaces(self) -> tuple[WorkspaceRecord, ...]:
        return tuple(
            self._workspaces[key]
            for key in sorted(self._workspaces, key=lambda item: (item[0], item[1]))
        )

    @property
    def membership_grants(self) -> tuple[MembershipGrant, ...]:
        return self._membership_grants

    @property
    def service_accounts(self) -> tuple[ServiceAccountRecord, ...]:
        return tuple(self._service_accounts[key] for key in sorted(self._service_accounts))

    @property
    def api_keys(self) -> tuple[ApiKeyRecord, ...]:
        return tuple(self._api_keys[key] for key in sorted(self._api_keys))

    def tenant(self, tenant_id: str) -> TenantRecord | None:
        return self._tenants.get(tenant_id)

    def workspace(self, tenant_id: str, workspace_id: str) -> WorkspaceRecord | None:
        return self._workspaces.get((tenant_id, workspace_id))

    def service_account(self, service_account_id: str) -> ServiceAccountRecord | None:
        return self._service_accounts.get(service_account_id)

    def evaluate_identity(
        self,
        *,
        user_id: str,
        tenant_id: str,
        workspace_id: str,
        requested_roles: Iterable[Role],
        email: str | None = None,
        break_glass_reason: str | None = None,
        evaluated_at: str | None = None,
    ) -> TenantGovernanceDecision:
        user_id = user_id.strip()
        tenant_id = tenant_id.strip()
        workspace_id = workspace_id.strip()
        requested_role_tuple = _unique_roles(requested_roles)
        if not user_id or not tenant_id or not workspace_id:
            return _deny("missing_identity_scope")
        if not requested_role_tuple:
            return _deny("no_requested_roles")

        tenant = self._tenants.get(tenant_id)
        if tenant is None:
            return _deny("tenant_not_registered")
        if tenant.status != TenantStatus.ACTIVE:
            return _deny("tenant_not_active")
        service_account = self._service_accounts.get(user_id)
        is_service_account = (
            service_account is not None
            and service_account.tenant_id == tenant_id
            and service_account.status == ServiceAccountStatus.ACTIVE
        )
        if not is_service_account and not _email_allowed(email, tenant.allowed_email_domains):
            return _deny("email_domain_not_allowed")

        if workspace_id != "*":
            workspace = self._workspaces.get((tenant_id, workspace_id))
            if workspace is None:
                return _deny("workspace_not_registered")
            if workspace.status != WorkspaceStatus.ACTIVE:
                return _deny("workspace_not_active")

        now = _parse_timestamp(evaluated_at) if evaluated_at else datetime.now(timezone.utc)
        matching_grants = [
            grant
            for grant in self._membership_grants
            if grant.user_id == user_id
            and grant.tenant_id == tenant_id
            and _grant_workspace_matches(grant.workspace_id, workspace_id)
            and _grant_is_active(grant, now)
        ]
        if not matching_grants:
            return _deny("no_active_membership_grant")

        effective_memberships: list[WorkspaceMembership] = []
        effective_roles: list[Role] = []
        matched_grant_ids: list[str] = []
        access_modes: list[AccessMode] = []
        for grant in matching_grants:
            granted_requested_roles = tuple(
                role for role in grant.roles if role in requested_role_tuple
            )
            if not granted_requested_roles:
                continue
            if grant.access_mode == AccessMode.BREAK_GLASS and not _has_text(
                break_glass_reason
            ):
                continue
            effective_memberships.append(
                WorkspaceMembership(
                    tenant_id=grant.tenant_id,
                    workspace_id=grant.workspace_id,
                    roles=granted_requested_roles,
                )
            )
            effective_roles.extend(granted_requested_roles)
            matched_grant_ids.append(grant.grant_id)
            access_modes.append(grant.access_mode)

        if not effective_memberships:
            if any(grant.access_mode == AccessMode.BREAK_GLASS for grant in matching_grants):
                return _deny("break_glass_reason_required")
            return _deny("requested_role_not_granted")

        return TenantGovernanceDecision(
            allowed=True,
            reason="identity_entitled",
            principal=Principal(user_id=user_id, memberships=tuple(effective_memberships)),
            effective_roles=_unique_roles(effective_roles),
            matched_grant_ids=tuple(matched_grant_ids),
            access_modes=tuple(dict.fromkeys(access_modes)),
            break_glass_reason=break_glass_reason.strip() if break_glass_reason else None,
        )

    def authenticate_api_key(
        self,
        raw_api_key: str,
        *,
        issuer: str,
        audience: str,
        evaluated_at: str | None = None,
    ) -> ApiKeyAuthenticationDecision:
        raw_api_key = raw_api_key.strip()
        if not raw_api_key:
            return ApiKeyAuthenticationDecision(allowed=False, reason="api_key_missing")
        now = _parse_timestamp(evaluated_at) if evaluated_at else datetime.now(timezone.utc)
        for api_key in self.api_keys:
            if not _api_key_secret_matches(raw_api_key, api_key.secret_hash):
                continue
            if api_key.status != ApiKeyStatus.ACTIVE:
                return ApiKeyAuthenticationDecision(
                    allowed=False,
                    reason="api_key_not_active",
                    key_id=api_key.key_id,
                    service_account_id=api_key.service_account_id,
                )
            if api_key.expires_at is not None and _parse_timestamp(api_key.expires_at) <= now:
                return ApiKeyAuthenticationDecision(
                    allowed=False,
                    reason="api_key_expired",
                    key_id=api_key.key_id,
                    service_account_id=api_key.service_account_id,
                )
            service_account = self._service_accounts.get(api_key.service_account_id)
            if service_account is None:
                return ApiKeyAuthenticationDecision(
                    allowed=False,
                    reason="service_account_not_registered",
                    key_id=api_key.key_id,
                    service_account_id=api_key.service_account_id,
                )
            if service_account.status != ServiceAccountStatus.ACTIVE:
                return ApiKeyAuthenticationDecision(
                    allowed=False,
                    reason="service_account_not_active",
                    key_id=api_key.key_id,
                    service_account_id=api_key.service_account_id,
                )
            if service_account.tenant_id != api_key.tenant_id:
                return ApiKeyAuthenticationDecision(
                    allowed=False,
                    reason="service_account_tenant_mismatch",
                    key_id=api_key.key_id,
                    service_account_id=api_key.service_account_id,
                )
            claims = {
                "iss": issuer,
                "aud": audience,
                "sub": api_key.service_account_id,
                "vyu": {
                    "tenant_id": api_key.tenant_id,
                    "workspace_id": api_key.workspace_id,
                    "roles": [role.value for role in api_key.roles],
                    "api_key_id": api_key.key_id,
                    "service_account_id": api_key.service_account_id,
                    "service_account_scopes": list(service_account.allowed_scopes),
                    "api_key_scopes": list(api_key.allowed_scopes),
                },
            }
            return ApiKeyAuthenticationDecision(
                allowed=True,
                reason="api_key_authenticated",
                claims=claims,
                key_id=api_key.key_id,
                service_account_id=api_key.service_account_id,
            )
        return ApiKeyAuthenticationDecision(allowed=False, reason="api_key_not_found")

    def require_identity(self, **kwargs: Any) -> TenantGovernanceDecision:
        decision = self.evaluate_identity(**kwargs)
        if not decision.allowed:
            raise PermissionError(f"Identity is not entitled: {decision.reason}")
        return decision

    def with_tenant(self, tenant: TenantRecord) -> "TenantGovernanceRegistry":
        tenants = {item.tenant_id: item for item in self.tenants}
        tenants[tenant.tenant_id] = tenant
        return TenantGovernanceRegistry(
            tenants=tenants.values(),
            workspaces=self.workspaces,
            membership_grants=self.membership_grants,
            service_accounts=self.service_accounts,
            api_keys=self.api_keys,
        )

    def with_workspace(self, workspace: WorkspaceRecord) -> "TenantGovernanceRegistry":
        workspaces = {(item.tenant_id, item.workspace_id): item for item in self.workspaces}
        workspaces[(workspace.tenant_id, workspace.workspace_id)] = workspace
        return TenantGovernanceRegistry(
            tenants=self.tenants,
            workspaces=workspaces.values(),
            membership_grants=self.membership_grants,
            service_accounts=self.service_accounts,
            api_keys=self.api_keys,
        )

    def with_membership_grant(self, grant: MembershipGrant) -> "TenantGovernanceRegistry":
        grants = {item.grant_id: item for item in self.membership_grants}
        grants[grant.grant_id] = grant
        return TenantGovernanceRegistry(
            tenants=self.tenants,
            workspaces=self.workspaces,
            membership_grants=grants.values(),
            service_accounts=self.service_accounts,
            api_keys=self.api_keys,
        )

    def with_service_account(self, service_account: ServiceAccountRecord) -> "TenantGovernanceRegistry":
        service_accounts = {item.service_account_id: item for item in self.service_accounts}
        service_accounts[service_account.service_account_id] = service_account
        return TenantGovernanceRegistry(
            tenants=self.tenants,
            workspaces=self.workspaces,
            membership_grants=self.membership_grants,
            service_accounts=service_accounts.values(),
            api_keys=self.api_keys,
        )

    def with_api_key(self, api_key: ApiKeyRecord) -> "TenantGovernanceRegistry":
        api_keys = {item.key_id: item for item in self.api_keys}
        api_keys[api_key.key_id] = api_key
        return TenantGovernanceRegistry(
            tenants=self.tenants,
            workspaces=self.workspaces,
            membership_grants=self.membership_grants,
            service_accounts=self.service_accounts,
            api_keys=api_keys.values(),
        )

    def revoked_membership_grant(
        self,
        grant_id: str,
        *,
        revoked_by: str = "",
        revoked_at: str = "",
    ) -> "TenantGovernanceRegistry":
        grants = {item.grant_id: item for item in self.membership_grants}
        grant = grants.get(grant_id)
        if grant is None:
            raise KeyError(f"Unknown membership grant: {grant_id}")
        metadata = dict(grant.metadata)
        if revoked_by:
            metadata["revoked_by"] = revoked_by
        if revoked_at:
            metadata["revoked_at"] = revoked_at
        grants[grant_id] = MembershipGrant(
            grant_id=grant.grant_id,
            user_id=grant.user_id,
            tenant_id=grant.tenant_id,
            workspace_id=grant.workspace_id,
            roles=grant.roles,
            status=MembershipGrantStatus.REVOKED,
            access_mode=grant.access_mode,
            granted_by=grant.granted_by,
            granted_at=grant.granted_at,
            expires_at=grant.expires_at,
            reason=grant.reason,
            metadata=metadata,
        )
        return TenantGovernanceRegistry(
            tenants=self.tenants,
            workspaces=self.workspaces,
            membership_grants=grants.values(),
            service_accounts=self.service_accounts,
            api_keys=self.api_keys,
        )

    def to_json(self, *, redact_api_key_hashes: bool = False) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "tenants": [tenant.to_json() for tenant in self.tenants],
            "workspaces": [workspace.to_json() for workspace in self.workspaces],
            "membership_grants": [grant.to_json() for grant in self.membership_grants],
            "service_accounts": [account.to_json() for account in self.service_accounts],
            "api_keys": [
                key.to_json(redact_secret_hash=redact_api_key_hashes)
                for key in self.api_keys
            ],
        }

    def to_safe_json(self) -> dict[str, Any]:
        return self.to_json(redact_api_key_hashes=True)

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "TenantGovernanceRegistry":
        schema_version = int(payload.get("schema_version", 1))
        if schema_version not in {1, 2}:
            raise ValueError("Unsupported tenant governance registry schema version.")
        return cls(
            tenants=(TenantRecord.from_json(item) for item in payload.get("tenants", [])),
            workspaces=(WorkspaceRecord.from_json(item) for item in payload.get("workspaces", [])),
            membership_grants=(
                MembershipGrant.from_json(item)
                for item in payload.get("membership_grants", [])
            ),
            service_accounts=(
                ServiceAccountRecord.from_json(item)
                for item in payload.get("service_accounts", [])
            ),
            api_keys=(ApiKeyRecord.from_json(item) for item in payload.get("api_keys", [])),
        )

    @classmethod
    def read(cls, path: Path) -> "TenantGovernanceRegistry":
        return cls.from_json(json.loads(path.read_text(encoding="utf-8")))

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_json(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


class TenantGovernanceRepository:
    """Reloadable JSON-backed tenant governance repository for deployed runtimes."""

    def __init__(self, path: Path):
        self.path = path

    def read(self) -> TenantGovernanceRegistry:
        return TenantGovernanceRegistry.read(self.path)

    def write(self, registry: TenantGovernanceRegistry) -> None:
        registry.write(self.path)

    def evaluate_identity(self, **kwargs: Any) -> TenantGovernanceDecision:
        return self.read().evaluate_identity(**kwargs)

    def authenticate_api_key(self, *args: Any, **kwargs: Any) -> ApiKeyAuthenticationDecision:
        return self.read().authenticate_api_key(*args, **kwargs)

    def upsert_tenant(self, tenant: TenantRecord) -> TenantGovernanceRegistry:
        registry = self.read().with_tenant(tenant)
        self.write(registry)
        return registry

    def upsert_workspace(self, workspace: WorkspaceRecord) -> TenantGovernanceRegistry:
        registry = self.read().with_workspace(workspace)
        self.write(registry)
        return registry

    def upsert_membership_grant(self, grant: MembershipGrant) -> TenantGovernanceRegistry:
        registry = self.read().with_membership_grant(grant)
        self.write(registry)
        return registry

    def revoke_membership_grant(
        self,
        grant_id: str,
        *,
        revoked_by: str = "",
        revoked_at: str = "",
    ) -> TenantGovernanceRegistry:
        registry = self.read().revoked_membership_grant(
            grant_id,
            revoked_by=revoked_by,
            revoked_at=revoked_at,
        )
        self.write(registry)
        return registry

    def upsert_service_account(
        self,
        service_account: ServiceAccountRecord,
    ) -> TenantGovernanceRegistry:
        registry = self.read().with_service_account(service_account)
        self.write(registry)
        return registry

    def upsert_api_key(self, api_key: ApiKeyRecord) -> TenantGovernanceRegistry:
        registry = self.read().with_api_key(api_key)
        self.write(registry)
        return registry


def hash_api_key_secret(raw_secret: str) -> str:
    raw_secret = raw_secret.strip()
    if not raw_secret:
        raise ValueError("API key secret cannot be empty.")
    digest = hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _deny(reason: str) -> TenantGovernanceDecision:
    return TenantGovernanceDecision(allowed=False, reason=reason)


def _grant_workspace_matches(grant_workspace_id: str, requested_workspace_id: str) -> bool:
    if requested_workspace_id == "*":
        return grant_workspace_id == "*"
    return grant_workspace_id in {requested_workspace_id, "*"}


def _grant_is_active(grant: MembershipGrant, now: datetime) -> bool:
    if grant.status != MembershipGrantStatus.ACTIVE:
        return False
    if grant.expires_at is None:
        return True
    return _parse_timestamp(grant.expires_at) > now


def _parse_timestamp(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _email_allowed(email: str | None, domains: tuple[str, ...]) -> bool:
    if not domains:
        return True
    if not email or "@" not in email:
        return False
    domain = _normalize_domain(email.rsplit("@", 1)[1])
    return domain in domains


def _normalize_domain(domain: Any) -> str:
    return str(domain).strip().lower().lstrip("@")


def _unique_roles(roles: Iterable[Role]) -> tuple[Role, ...]:
    seen: set[Role] = set()
    result: list[Role] = []
    for role in roles:
        if role not in seen:
            seen.add(role)
            result.append(role)
    return tuple(result)


def _has_text(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def _api_key_secret_matches(raw_api_key: str, stored_hash: str) -> bool:
    if not stored_hash.startswith("sha256:"):
        return False
    return hmac.compare_digest(hash_api_key_secret(raw_api_key), stored_hash)
