from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from src.vyu.authz import Role


class IdentityMappingError(ValueError):
    """Raised when trusted upstream identity claims cannot be mapped to Vyu."""


@dataclass(frozen=True)
class MappedIdentity:
    user_id: str
    tenant_id: str
    workspace_id: str
    role: Role
    source_subject: str
    issuer: str
    audience: tuple[str, ...]
    email: str | None = None
    governed_grant_ids: tuple[str, ...] = ()
    governed_access_modes: tuple[str, ...] = ()
    break_glass_reason: str | None = None

    def to_service_headers(self) -> dict[str, str]:
        headers = {
            "x-vyu-user-id": self.user_id,
            "x-vyu-tenant-id": self.tenant_id,
            "x-vyu-workspace-id": self.workspace_id,
            "x-vyu-role": self.role.value,
        }
        if self.governed_grant_ids:
            headers["x-vyu-governed-grant-ids"] = ",".join(self.governed_grant_ids)
        if self.governed_access_modes:
            headers["x-vyu-access-modes"] = ",".join(self.governed_access_modes)
        if self.break_glass_reason:
            headers["x-vyu-break-glass-reason"] = self.break_glass_reason
        return headers


@dataclass(frozen=True)
class IdentityMappingDecision:
    mapped_identity: MappedIdentity
    mapped_role_claims: tuple[str, ...]
    ignored_role_claims: tuple[str, ...]

    def to_service_headers(self) -> dict[str, str]:
        return self.mapped_identity.to_service_headers()


@dataclass(frozen=True)
class IdentityMappingConfig:
    """Configuration for mapping trusted deployed identity claims into Vyu."""

    trusted_issuers: frozenset[str]
    accepted_audiences: frozenset[str]
    user_id_claim: str = "sub"
    tenant_id_claim: str = "vyu.tenant_id"
    tenant_id_fallback_claims: tuple[str, ...] = ("custom:vyu_tenant_id",)
    workspace_id_claim: str = "vyu.workspace_id"
    workspace_id_fallback_claims: tuple[str, ...] = ("custom:vyu_workspace_id",)
    role_claims: tuple[str, ...] = (
        "vyu.roles",
        "roles",
        "groups",
        "cognito:groups",
        "custom:vyu_roles",
    )
    email_claim: str = "email"
    email_verified_claim: str = "email_verified"
    require_email_verified: bool = False
    role_mappings: Mapping[str, Role] = field(default_factory=lambda: DEFAULT_ROLE_MAPPINGS)
    tenant_governance: Any | None = None
    break_glass_reason_claim: str = "vyu.break_glass_reason"


DEFAULT_ROLE_MAPPINGS: dict[str, Role] = {
    "researcher": Role.RESEARCHER,
    "vyu:researcher": Role.RESEARCHER,
    "reviewer": Role.REVIEWER,
    "vyu:reviewer": Role.REVIEWER,
    "workspace_admin": Role.WORKSPACE_ADMIN,
    "workspace-admin": Role.WORKSPACE_ADMIN,
    "vyu:workspace_admin": Role.WORKSPACE_ADMIN,
    "vyu:workspace-admin": Role.WORKSPACE_ADMIN,
    "tenant_admin": Role.TENANT_ADMIN,
    "tenant-admin": Role.TENANT_ADMIN,
    "vyu:tenant_admin": Role.TENANT_ADMIN,
    "vyu:tenant-admin": Role.TENANT_ADMIN,
}

_ROLE_PRIORITY: tuple[Role, ...] = (
    Role.TENANT_ADMIN,
    Role.WORKSPACE_ADMIN,
    Role.REVIEWER,
    Role.RESEARCHER,
)


class IdentityMapper:
    def __init__(self, config: IdentityMappingConfig):
        if not config.trusted_issuers:
            raise ValueError("At least one trusted issuer is required.")
        if not config.accepted_audiences:
            raise ValueError("At least one accepted audience is required.")
        self.config = config

    def map_claims(self, claims: Mapping[str, Any]) -> IdentityMappingDecision:
        issuer = _required_string(claims, "iss")
        if issuer not in self.config.trusted_issuers:
            raise IdentityMappingError(f"Untrusted issuer: {issuer}.")

        audience = _audiences(claims.get("aud"))
        if not audience:
            raise IdentityMappingError("Missing audience claim: aud.")
        if not set(audience).intersection(self.config.accepted_audiences):
            raise IdentityMappingError(
                "Audience claim is not accepted by this Vyu deployment."
            )

        if self.config.require_email_verified:
            verified = _claim_at_path(claims, self.config.email_verified_claim)
            if verified is not True:
                raise IdentityMappingError("Email verification is required.")

        source_subject = _required_string(claims, self.config.user_id_claim)
        tenant_id = _required_string_from_claims(
            claims,
            (self.config.tenant_id_claim, *self.config.tenant_id_fallback_claims),
        )
        workspace_id = _required_string_from_claims(
            claims,
            (self.config.workspace_id_claim, *self.config.workspace_id_fallback_claims),
        )
        email = _optional_string(claims, self.config.email_claim)
        role, mapped_role_claims, ignored_role_claims, mapped_roles = self._map_role(claims)
        governed_grant_ids: tuple[str, ...] = ()
        governed_access_modes: tuple[str, ...] = ()
        break_glass_reason = _optional_string(claims, self.config.break_glass_reason_claim)

        if self.config.tenant_governance is not None:
            governance_decision = self.config.tenant_governance.evaluate_identity(
                user_id=source_subject,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                requested_roles=mapped_roles,
                email=email,
                break_glass_reason=break_glass_reason,
            )
            if not governance_decision.allowed:
                raise IdentityMappingError(
                    f"Tenant governance denied identity: {governance_decision.reason}."
                )
            role = _highest_priority_role(governance_decision.effective_roles)
            mapped_role_claims = tuple(
                raw for raw, mapped_role in self._mapped_role_pairs(claims) if mapped_role == role
            )
            governed_grant_ids = governance_decision.matched_grant_ids
            governed_access_modes = tuple(
                str(mode.value) for mode in governance_decision.access_modes
            )

        return IdentityMappingDecision(
            mapped_identity=MappedIdentity(
                user_id=source_subject,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                role=role,
                source_subject=source_subject,
                issuer=issuer,
                audience=audience,
                email=email,
                governed_grant_ids=governed_grant_ids,
                governed_access_modes=governed_access_modes,
                break_glass_reason=break_glass_reason,
            ),
            mapped_role_claims=mapped_role_claims,
            ignored_role_claims=ignored_role_claims,
        )

    def map_to_service_headers(
        self,
        claims: Mapping[str, Any],
        existing_headers: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        headers = {str(key).lower(): str(value) for key, value in (existing_headers or {}).items()}
        mapped = self.map_claims(claims).to_service_headers()
        headers.update(mapped)
        return headers

    def _map_role(
        self,
        claims: Mapping[str, Any],
    ) -> tuple[Role, tuple[str, ...], tuple[str, ...], tuple[Role, ...]]:
        mapped, ignored = self._role_claim_mapping(claims)
        if not mapped:
            raise IdentityMappingError("No trusted role claim mapped to a Vyu role.")

        mapped_roles = _unique_roles(role for _, role in mapped)
        chosen = _highest_priority_role(mapped_roles)
        return (
            chosen,
            tuple(raw for raw, role in mapped if role == chosen),
            tuple(ignored),
            mapped_roles,
        )

    def _mapped_role_pairs(self, claims: Mapping[str, Any]) -> tuple[tuple[str, Role], ...]:
        mapped, _ignored = self._role_claim_mapping(claims)
        return tuple(mapped)

    def _role_claim_mapping(
        self,
        claims: Mapping[str, Any],
    ) -> tuple[list[tuple[str, Role]], list[str]]:
        raw_role_values: list[str] = []
        for claim_path in self.config.role_claims:
            claim_value = _claim_at_path(claims, claim_path)
            raw_role_values.extend(_role_values(claim_value))

        mapped: list[tuple[str, Role]] = []
        ignored: list[str] = []
        normalized_mapping = {
            str(external).strip().lower(): role
            for external, role in self.config.role_mappings.items()
        }
        for raw in raw_role_values:
            key = raw.strip().lower()
            role = normalized_mapping.get(key)
            if role is None:
                ignored.append(raw)
            else:
                mapped.append((raw, role))
        return mapped, ignored


def _unique_roles(roles: Any) -> tuple[Role, ...]:
    seen: set[Role] = set()
    result: list[Role] = []
    for role in roles:
        if role not in seen:
            seen.add(role)
            result.append(role)
    return tuple(result)


def _highest_priority_role(roles: Any) -> Role:
    role_set = set(roles)
    for role in _ROLE_PRIORITY:
        if role in role_set:
            return role
    raise IdentityMappingError("No trusted role claim mapped to a Vyu role.")


def _required_string(claims: Mapping[str, Any], claim_path: str) -> str:
    return _required_string_from_claims(claims, (claim_path,))


def _required_string_from_claims(
    claims: Mapping[str, Any],
    claim_paths: tuple[str, ...],
) -> str:
    for claim_path in claim_paths:
        value = _claim_at_path(claims, claim_path)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise IdentityMappingError(
        "Missing required identity claim: " + " or ".join(claim_paths) + "."
    )


def _optional_string(claims: Mapping[str, Any], claim_path: str) -> str | None:
    value = _claim_at_path(claims, claim_path)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _claim_at_path(claims: Mapping[str, Any], claim_path: str) -> Any:
    if claim_path in claims:
        return claims[claim_path]
    current: Any = claims
    for part in claim_path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _audiences(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _role_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value)] if str(value).strip() else []
