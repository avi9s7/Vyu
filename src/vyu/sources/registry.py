from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProductionSourceRecord:
    source_id: str
    display_name: str
    source_type: str
    owner: str
    license_or_terms: str
    allowed_uses: list[str]
    forbidden_uses: list[str] = field(default_factory=list)
    attribution_required: bool = False
    retention_policy: str = ""
    update_cadence: str = ""
    phi_pii_status: str = "none"
    access_policy: str = ""
    connector_config_ref: str = ""
    rate_limit_policy: str = ""
    approval_status: str = "draft"
    approved_by: str = ""
    approved_at: str = ""
    source_version: str = "v1"
    policy_version: str = "source_governance_policy_v1"

    def to_json(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "display_name": self.display_name,
            "source_type": self.source_type,
            "owner": self.owner,
            "license_or_terms": self.license_or_terms,
            "allowed_uses": list(self.allowed_uses),
            "forbidden_uses": list(self.forbidden_uses),
            "attribution_required": self.attribution_required,
            "retention_policy": self.retention_policy,
            "update_cadence": self.update_cadence,
            "phi_pii_status": self.phi_pii_status,
            "access_policy": self.access_policy,
            "connector_config_ref": self.connector_config_ref,
            "rate_limit_policy": self.rate_limit_policy,
            "approval_status": self.approval_status,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "source_version": self.source_version,
            "policy_version": self.policy_version,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ProductionSourceRecord":
        return cls(
            source_id=str(payload["source_id"]),
            display_name=str(payload["display_name"]),
            source_type=str(payload["source_type"]),
            owner=str(payload["owner"]),
            license_or_terms=str(payload["license_or_terms"]),
            allowed_uses=list(payload["allowed_uses"]),
            forbidden_uses=list(payload.get("forbidden_uses", [])),
            attribution_required=bool(payload.get("attribution_required", False)),
            retention_policy=str(payload.get("retention_policy", "")),
            update_cadence=str(payload.get("update_cadence", "")),
            phi_pii_status=str(payload.get("phi_pii_status", "none")),
            access_policy=str(payload.get("access_policy", "")),
            connector_config_ref=str(payload.get("connector_config_ref", "")),
            rate_limit_policy=str(payload.get("rate_limit_policy", "")),
            approval_status=str(payload.get("approval_status", "draft")),
            approved_by=str(payload.get("approved_by", "")),
            approved_at=str(payload.get("approved_at", "")),
            source_version=str(payload.get("source_version", "v1")),
            policy_version=str(payload.get("policy_version", "source_governance_policy_v1")),
        )

    @property
    def approved(self) -> bool:
        return self.approval_status == "approved" and bool(self.approved_by) and bool(self.approved_at)

    def allows_use(self, intended_use: str) -> bool:
        return intended_use in self.allowed_uses and intended_use not in self.forbidden_uses

    def allows_scope(self, tenant_id: str | None = None, workspace_id: str | None = None) -> bool:
        """Return whether this source can be used by a tenant/workspace scope.

        The current production registry stores access rules as compact policy labels so the
        source registry remains portable JSON. Supported labels are intentionally simple and
        fail closed when a scoped policy cannot be evaluated:

        - empty, ``all``, ``all_approved_workspaces``
        - ``tenant:<tenant_id>``
        - ``workspace:<workspace_id>``
        - ``workspace:<tenant_id>/<workspace_id>``
        - ``tenant:<tenant_id>:workspace:<workspace_id>``
        """
        policy = self.access_policy.strip()
        if not policy or policy in {"all", "all_approved_workspaces"}:
            return True
        if tenant_id is None and workspace_id is None:
            return False

        allowed_tokens = {token.strip() for token in policy.split(",") if token.strip()}
        if "all" in allowed_tokens or "all_approved_workspaces" in allowed_tokens:
            return True
        if tenant_id is not None and f"tenant:{tenant_id}" in allowed_tokens:
            return True
        if workspace_id is not None and f"workspace:{workspace_id}" in allowed_tokens:
            return True
        if tenant_id is not None and workspace_id is not None:
            return (
                f"workspace:{tenant_id}/{workspace_id}" in allowed_tokens
                or f"tenant:{tenant_id}:workspace:{workspace_id}" in allowed_tokens
            )
        return False


class SourceRegistry:
    def __init__(self, sources: list[ProductionSourceRecord]):
        self._sources = {source.source_id: source for source in sources}
        if len(self._sources) != len(sources):
            raise ValueError("Source registry contains duplicate source_id values.")

    def source_ids(self) -> list[str]:
        return sorted(self._sources)

    def get(self, source_id: str) -> ProductionSourceRecord:
        try:
            return self._sources[source_id]
        except KeyError as exc:
            raise KeyError(f"Unknown production source: {source_id}") from exc

    def require_approved(
        self,
        source_id: str,
        intended_use: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> ProductionSourceRecord:
        source = self.get(source_id)
        if not source.approved:
            raise PermissionError(
                f"Source {source_id!r} is not approved for production use "
                f"(status={source.approval_status!r})."
            )
        if intended_use is not None and not source.allows_use(intended_use):
            raise PermissionError(
                f"Source {source_id!r} is not approved for use {intended_use!r}."
            )
        if not source.allows_scope(tenant_id=tenant_id, workspace_id=workspace_id):
            raise PermissionError(
                f"Source {source_id!r} is not approved for tenant/workspace scope "
                f"tenant={tenant_id!r}, workspace={workspace_id!r}."
            )
        return source

    def to_json(self) -> dict[str, Any]:
        return {"sources": [self._sources[source_id].to_json() for source_id in self.source_ids()]}

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "SourceRegistry":
        return cls(
            [
                ProductionSourceRecord.from_json(source)
                for source in payload.get("sources", [])
            ]
        )

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json(), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @classmethod
    def read(cls, path: Path) -> "SourceRegistry":
        return cls.from_json(json.loads(path.read_text(encoding="utf-8")))
