from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Action(StrEnum):
    READ_ARTIFACT = "read_artifact"
    READ_AUDIT_EVENT = "read_audit_event"
    RUN_RESEARCH = "run_research"
    REVIEW_OUTPUT = "review_output"
    EXPORT_REPORT = "export_report"
    MANAGE_SOURCES = "manage_sources"
    MANAGE_WORKSPACE = "manage_workspace"
    MANAGE_TENANT = "manage_tenant"
    MANAGE_SERVICE_ACCOUNTS = "manage_service_accounts"
    MANAGE_API_KEYS = "manage_api_keys"


class Role(StrEnum):
    RESEARCHER = "researcher"
    REVIEWER = "reviewer"
    WORKSPACE_ADMIN = "workspace_admin"
    TENANT_ADMIN = "tenant_admin"


@dataclass(frozen=True)
class ResourceScope:
    tenant_id: str
    workspace_id: str


@dataclass(frozen=True)
class WorkspaceMembership:
    tenant_id: str
    workspace_id: str
    roles: tuple[Role, ...]


@dataclass(frozen=True)
class Principal:
    user_id: str
    memberships: tuple[WorkspaceMembership, ...]


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason: str
    matched_role: Role | None = None


class AuthorizationPolicy:
    def __init__(
        self,
        role_permissions: dict[Role, frozenset[Action]] | None = None,
    ):
        self.role_permissions = role_permissions or _DEFAULT_ROLE_PERMISSIONS

    def authorize(
        self,
        principal: Principal,
        action: Action,
        scope: ResourceScope,
    ) -> AuthorizationDecision:
        matching_roles = [
            role
            for membership in principal.memberships
            if _scope_matches(membership, scope)
            for role in membership.roles
        ]
        if not matching_roles:
            return AuthorizationDecision(allowed=False, reason="no_matching_scope")

        for role in matching_roles:
            if action in self.role_permissions.get(role, frozenset()):
                return AuthorizationDecision(
                    allowed=True,
                    reason="role_allows_action",
                    matched_role=role,
                )
        return AuthorizationDecision(
            allowed=False,
            reason="role_missing_action",
        )

    def require(
        self,
        principal: Principal,
        action: Action,
        scope: ResourceScope,
    ) -> AuthorizationDecision:
        decision = self.authorize(principal, action, scope)
        if not decision.allowed:
            raise PermissionError(
                f"Principal {principal.user_id!r} is not authorized for "
                f"{action.value!r} in tenant {scope.tenant_id!r} workspace "
                f"{scope.workspace_id!r}: {decision.reason}"
            )
        return decision


_DEFAULT_ROLE_PERMISSIONS: dict[Role, frozenset[Action]] = {
    Role.RESEARCHER: frozenset(
        {
            Action.READ_ARTIFACT,
            Action.READ_AUDIT_EVENT,
            Action.RUN_RESEARCH,
        }
    ),
    Role.REVIEWER: frozenset(
        {
            Action.READ_ARTIFACT,
            Action.READ_AUDIT_EVENT,
            Action.RUN_RESEARCH,
            Action.REVIEW_OUTPUT,
            Action.EXPORT_REPORT,
        }
    ),
    Role.WORKSPACE_ADMIN: frozenset(
        {
            Action.READ_ARTIFACT,
            Action.READ_AUDIT_EVENT,
            Action.RUN_RESEARCH,
            Action.REVIEW_OUTPUT,
            Action.EXPORT_REPORT,
            Action.MANAGE_WORKSPACE,
        }
    ),
    Role.TENANT_ADMIN: frozenset(Action),
}


def _scope_matches(membership: WorkspaceMembership, scope: ResourceScope) -> bool:
    if membership.tenant_id != scope.tenant_id:
        return False
    return membership.workspace_id == scope.workspace_id or membership.workspace_id == "*"


from src.vyu.authz.tenant_governance import (
    AccessMode,
    MembershipGrant,
    MembershipGrantStatus,
    ApiKeyAuthenticationDecision,
    ApiKeyRecord,
    ApiKeyStatus,
    TenantGovernanceDecision,
    TenantGovernanceRegistry,
    TenantGovernanceRepository,
    TenantRecord,
    TenantStatus,
    ServiceAccountRecord,
    ServiceAccountStatus,
    WorkspaceRecord,
    WorkspaceStatus,
    hash_api_key_secret,
)

__all__ = [
    "AccessMode",
    "Action",
    "ApiKeyAuthenticationDecision",
    "ApiKeyRecord",
    "ApiKeyStatus",
    "ServiceAccountRecord",
    "ServiceAccountStatus",
    "TenantGovernanceRepository",
    "hash_api_key_secret",
    "AuthorizationDecision",
    "AuthorizationPolicy",
    "MembershipGrant",
    "MembershipGrantStatus",
    "Principal",
    "ResourceScope",
    "Role",
    "TenantGovernanceDecision",
    "TenantGovernanceRegistry",
    "TenantRecord",
    "TenantStatus",
    "WorkspaceMembership",
    "WorkspaceRecord",
    "WorkspaceStatus",
]
