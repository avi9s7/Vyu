from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.vyu.deployment.release_channel_target_decision import DEPLOYMENT_RELEASE_CHANNEL_TARGET_DECISION_SCHEMA

DEPLOYMENT_RELEASE_CHANNEL_PROVIDER_PREFLIGHT_SCHEMA = 1
DEFAULT_RELEASE_CHANNEL_PROVIDER_PREFLIGHT_NAME = "local-release-channel-provider-planning-preflight"
DEFAULT_RELEASE_CHANNEL_PROVIDER_PLANNING_REQUIREMENTS = (
    "Identity and authorization boundary reviewed for the selected target family.",
    "Ingress, egress, TLS, and network exposure requirements identified without provider configuration.",
    "Observability, audit, and alerting expectations identified without creating dashboards or cloud resources.",
    "Rollback and incident-response expectations identified before any provider-specific implementation.",
    "Secrets, environment variables, and configuration handling requirements identified without recording secret values.",
    "Compliance evidence and operator approval requirements identified for the future provider-planning module.",
)
DEFAULT_RELEASE_CHANNEL_PROVIDER_PREFLIGHT_NEXT_ACTIONS = (
    "Create a provider-specific planning module only after the abstract target-family preflight is reviewed.",
    "Keep provider credentials and mutable cloud operations out of local release-channel evidence until explicitly scoped.",
    "Preserve the target decision record, target-readiness note, export summary, and release evidence chain with this preflight.",
    "Do not transfer, sign, upload, scan, persist to production storage, or deploy artifacts from this local preflight.",
)


class DeploymentReleaseChannelProviderPreflightError(RuntimeError):
    """Raised when release-channel provider-planning preflight metadata is invalid."""


@dataclass(frozen=True)
class DeploymentReleaseChannelProviderPreflightCheck:
    name: str
    passed: bool
    detail: str

    def to_json(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class DeploymentReleaseChannelTargetDecisionInput:
    path: Path
    sha256: str | None
    readable: bool
    json_valid: bool
    schema_version: int | None
    status: str | None
    decided_at: str | None
    decision_id: str | None

    def to_json(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "readable": self.readable,
            "json_valid": self.json_valid,
            "schema_version": self.schema_version,
            "status": self.status,
            "decided_at": self.decided_at,
            "decision_id": self.decision_id,
        }


@dataclass(frozen=True)
class DeploymentReleaseChannelProviderPreflight:
    created_at: str
    preflight_name: str
    target_decision_path: Path
    target_decision: DeploymentReleaseChannelTargetDecisionInput
    planning_scope: str
    selected_target_family: str | None
    selected_target_provider: str | None
    provider_configuration: dict[str, object]
    package: dict[str, object]
    target_operator: dict[str, object]
    inherited_operator: dict[str, object]
    decision: dict[str, object]
    target_selection_scope: str | None
    candidate_target_families: tuple[str, ...]
    export_summary: dict[str, object]
    evidence_hashes: dict[str, object]
    evidence_counts: dict[str, object]
    local_only_limits: tuple[str, ...]
    handoff_checklist: tuple[str, ...]
    planning_requirements: tuple[str, ...]
    next_actions: tuple[str, ...]
    checks: tuple[DeploymentReleaseChannelProviderPreflightCheck, ...] = field(default_factory=tuple)

    @property
    def status(self) -> str:
        return "ready" if all(check.passed for check in self.checks) else "blocked"

    @property
    def blocking_reasons(self) -> tuple[str, ...]:
        return tuple(check.name for check in self.checks if not check.passed)

    def to_json(self) -> dict[str, object]:
        passed = sum(1 for check in self.checks if check.passed)
        failed = len(self.checks) - passed
        return {
            "schema_version": DEPLOYMENT_RELEASE_CHANNEL_PROVIDER_PREFLIGHT_SCHEMA,
            "status": self.status,
            "created_at": self.created_at,
            "preflight_name": self.preflight_name,
            "target_decision_path": str(self.target_decision_path),
            "target_decision": self.target_decision.to_json(),
            "planning_scope": self.planning_scope,
            "selected_target_family": self.selected_target_family,
            "selected_target_provider": self.selected_target_provider,
            "provider_configuration": dict(self.provider_configuration),
            "package": dict(self.package),
            "target_operator": dict(self.target_operator),
            "inherited_operator": dict(self.inherited_operator),
            "decision": dict(self.decision),
            "target_selection_scope": self.target_selection_scope,
            "candidate_target_families": list(self.candidate_target_families),
            "export_summary": dict(self.export_summary),
            "evidence_hashes": dict(self.evidence_hashes),
            "evidence_counts": dict(self.evidence_counts),
            "local_only_limits": list(self.local_only_limits),
            "handoff_checklist": list(self.handoff_checklist),
            "planning_requirements": list(self.planning_requirements),
            "next_actions": list(self.next_actions),
            "blocking_reasons": list(self.blocking_reasons),
            "summary": {
                "passed": passed,
                "failed": failed,
                "total": len(self.checks),
                "planning_requirement_count": len(self.planning_requirements),
                "next_action_count": len(self.next_actions),
                "candidate_target_family_count": len(self.candidate_target_families),
            },
            "checks": [check.to_json() for check in self.checks],
        }


def build_deployment_release_channel_provider_preflight(
    *,
    target_decision_path: Path,
    root: Path = Path("."),
    preflight_name: str = DEFAULT_RELEASE_CHANNEL_PROVIDER_PREFLIGHT_NAME,
    created_at: str | None = None,
    planning_requirements: Sequence[str] = DEFAULT_RELEASE_CHANNEL_PROVIDER_PLANNING_REQUIREMENTS,
    next_actions: Sequence[str] = DEFAULT_RELEASE_CHANNEL_PROVIDER_PREFLIGHT_NEXT_ACTIONS,
) -> DeploymentReleaseChannelProviderPreflight:
    """Build a local provider-planning preflight from a selected abstract target-family decision."""

    root = Path(root)
    target_decision_path = Path(target_decision_path)
    preflight_name = _normalize_required_text(preflight_name, "preflight_name")
    created_at = _normalize_created_at(created_at)
    normalized_requirements = _normalize_text_sequence(planning_requirements, "planning_requirements")
    normalized_next_actions = _normalize_text_sequence(next_actions, "next_actions")

    payload, target_decision = _read_target_decision(target_decision_path, root=root)
    decision = dict(_mapping_value(payload, "decision") or {})
    selected_target_family = _str_or_none(decision.get("selected_target_family"))
    provider_configuration = dict(_mapping_value(payload, "provider_configuration") or {})
    candidate_target_families = tuple(_string_list_value(payload, "candidate_target_families"))
    checks = _build_checks(
        payload=payload,
        target_decision=target_decision,
        decision=decision,
        selected_target_family=selected_target_family,
        candidate_target_families=candidate_target_families,
        provider_configuration=provider_configuration,
        planning_requirements=normalized_requirements,
        next_actions=normalized_next_actions,
    )

    return DeploymentReleaseChannelProviderPreflight(
        created_at=created_at,
        preflight_name=preflight_name,
        target_decision_path=target_decision_path,
        target_decision=target_decision,
        planning_scope="provider_planning_preflight_only",
        selected_target_family=selected_target_family,
        selected_target_provider=_str_or_none(payload.get("selected_target_provider") if payload else None),
        provider_configuration=provider_configuration,
        package=dict(_mapping_value(payload, "package") or {}),
        target_operator=dict(_mapping_value(payload, "operator") or {}),
        inherited_operator=dict(_mapping_value(payload, "inherited_operator") or {}),
        decision=decision,
        target_selection_scope=_str_or_none(payload.get("target_selection_scope") if payload else None),
        candidate_target_families=candidate_target_families,
        export_summary=dict(_mapping_value(payload, "export_summary") or {}),
        evidence_hashes=dict(_mapping_value(payload, "evidence_hashes") or {}),
        evidence_counts=dict(_mapping_value(payload, "evidence_counts") or {}),
        local_only_limits=tuple(_string_list_value(payload, "local_only_limits")),
        handoff_checklist=tuple(_string_list_value(payload, "handoff_checklist")),
        planning_requirements=normalized_requirements,
        next_actions=normalized_next_actions,
        checks=checks,
    )


def write_deployment_release_channel_provider_preflight(
    preflight: DeploymentReleaseChannelProviderPreflight,
    output_path: Path,
) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(preflight.to_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _build_checks(
    *,
    payload: Mapping[str, object] | None,
    target_decision: DeploymentReleaseChannelTargetDecisionInput,
    decision: Mapping[str, object],
    selected_target_family: str | None,
    candidate_target_families: tuple[str, ...],
    provider_configuration: Mapping[str, object],
    planning_requirements: tuple[str, ...],
    next_actions: tuple[str, ...],
) -> tuple[DeploymentReleaseChannelProviderPreflightCheck, ...]:
    target_checks = _list_of_mappings(payload, "checks")
    failed_target_checks = [
        _str_or_none(check.get("name")) or "unnamed_check"
        for check in target_checks
        if check.get("passed") is not True
    ]
    target_blocking_reasons = _string_list_value(payload, "blocking_reasons")
    evidence_hashes = _mapping_value(payload, "evidence_hashes")
    return (
        DeploymentReleaseChannelProviderPreflightCheck(
            "target_decision_file_readable",
            target_decision.readable,
            str(target_decision.path),
        ),
        DeploymentReleaseChannelProviderPreflightCheck(
            "target_decision_json_valid",
            target_decision.json_valid,
            "valid" if target_decision.json_valid else "invalid",
        ),
        DeploymentReleaseChannelProviderPreflightCheck(
            "target_decision_schema_supported",
            target_decision.schema_version == DEPLOYMENT_RELEASE_CHANNEL_TARGET_DECISION_SCHEMA,
            f"schema_version={target_decision.schema_version}",
        ),
        DeploymentReleaseChannelProviderPreflightCheck(
            "target_decision_status_selected",
            target_decision.status == "selected",
            str(target_decision.status),
        ),
        DeploymentReleaseChannelProviderPreflightCheck(
            "target_decision_checks_passed",
            len(target_checks) > 0 and len(failed_target_checks) == 0,
            "failed=" + ",".join(failed_target_checks) if failed_target_checks else f"checks={len(target_checks)}",
        ),
        DeploymentReleaseChannelProviderPreflightCheck(
            "target_decision_blocking_reasons_absent",
            len(target_blocking_reasons) == 0,
            f"count={len(target_blocking_reasons)}",
        ),
        DeploymentReleaseChannelProviderPreflightCheck(
            "decision_value_choose",
            _str_or_none(decision.get("value")) == "choose",
            str(decision.get("value")),
        ),
        DeploymentReleaseChannelProviderPreflightCheck(
            "selected_target_family_present",
            bool(selected_target_family),
            str(selected_target_family),
        ),
        DeploymentReleaseChannelProviderPreflightCheck(
            "selected_target_family_in_candidates",
            bool(selected_target_family and selected_target_family in candidate_target_families),
            f"selected={selected_target_family},candidates={','.join(candidate_target_families)}",
        ),
        DeploymentReleaseChannelProviderPreflightCheck(
            "target_selection_scope_local_only",
            _str_or_none(payload.get("target_selection_scope") if payload else None) == "local_target_family_review_only",
            str(payload.get("target_selection_scope") if payload else None),
        ),
        DeploymentReleaseChannelProviderPreflightCheck(
            "no_target_provider_selected",
            _str_or_none(payload.get("selected_target_provider") if payload else None) is None,
            "selected_target_provider=None",
        ),
        DeploymentReleaseChannelProviderPreflightCheck(
            "no_provider_configuration_recorded",
            len(provider_configuration) == 0,
            f"keys={len(provider_configuration)}",
        ),
        DeploymentReleaseChannelProviderPreflightCheck(
            "export_summary_sha256_present",
            bool(_nested_str(payload, "export_summary", "sha256")),
            "export_summary.sha256",
        ),
        DeploymentReleaseChannelProviderPreflightCheck(
            "evidence_index_sha256_present",
            bool(_str_or_none(evidence_hashes.get("evidence_index_sha256") if evidence_hashes else None)),
            "evidence_hashes.evidence_index_sha256",
        ),
        DeploymentReleaseChannelProviderPreflightCheck(
            "package_metadata_present",
            _package_metadata_present(_mapping_value(payload, "package")),
            "package_name,runtime,handler",
        ),
        DeploymentReleaseChannelProviderPreflightCheck(
            "target_operator_metadata_present",
            _operator_metadata_present(_mapping_value(payload, "operator")),
            "operator.id,operator.role",
        ),
        DeploymentReleaseChannelProviderPreflightCheck(
            "local_only_limits_present",
            len(_string_list_value(payload, "local_only_limits")) > 0,
            f"count={len(_string_list_value(payload, 'local_only_limits'))}",
        ),
        DeploymentReleaseChannelProviderPreflightCheck(
            "handoff_checklist_present",
            len(_string_list_value(payload, "handoff_checklist")) > 0,
            f"count={len(_string_list_value(payload, 'handoff_checklist'))}",
        ),
        DeploymentReleaseChannelProviderPreflightCheck(
            "planning_requirements_recorded",
            len(planning_requirements) > 0,
            f"count={len(planning_requirements)}",
        ),
        DeploymentReleaseChannelProviderPreflightCheck(
            "next_actions_present",
            len(next_actions) > 0,
            f"count={len(next_actions)}",
        ),
    )


def _read_target_decision(
    path: Path,
    *,
    root: Path,
) -> tuple[Mapping[str, object] | None, DeploymentReleaseChannelTargetDecisionInput]:
    path = Path(path)
    file_path = path if path.is_absolute() else root / path
    sha256 = _sha256(file_path) if file_path.is_file() else None
    if not file_path.is_file():
        return None, DeploymentReleaseChannelTargetDecisionInput(
            path=path,
            sha256=None,
            readable=False,
            json_valid=False,
            schema_version=None,
            status=None,
            decided_at=None,
            decision_id=None,
        )
    try:
        payload: Any = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, DeploymentReleaseChannelTargetDecisionInput(
            path=path,
            sha256=sha256,
            readable=True,
            json_valid=False,
            schema_version=None,
            status=None,
            decided_at=None,
            decision_id=None,
        )
    if not isinstance(payload, Mapping):
        return None, DeploymentReleaseChannelTargetDecisionInput(
            path=path,
            sha256=sha256,
            readable=True,
            json_valid=False,
            schema_version=None,
            status=None,
            decided_at=None,
            decision_id=None,
        )
    return payload, DeploymentReleaseChannelTargetDecisionInput(
        path=path,
        sha256=sha256,
        readable=True,
        json_valid=True,
        schema_version=_optional_int(payload.get("schema_version")),
        status=_str_or_none(payload.get("status")),
        decided_at=_str_or_none(payload.get("decided_at")),
        decision_id=_str_or_none(payload.get("decision_id")),
    )


def _nested_str(payload: Mapping[str, object] | None, parent: str, key: str) -> str | None:
    value = _mapping_value(payload, parent)
    return _str_or_none(value.get(key) if value else None)


def _package_metadata_present(package: Mapping[str, object] | None) -> bool:
    if package is None:
        return False
    return all(bool(_str_or_none(package.get(key))) for key in ("package_name", "runtime", "handler"))


def _operator_metadata_present(operator: Mapping[str, object] | None) -> bool:
    if operator is None:
        return False
    return bool(_str_or_none(operator.get("id")) and _str_or_none(operator.get("role")))


def _mapping_value(payload: Mapping[str, object] | None, key: str) -> Mapping[str, object] | None:
    if payload is None:
        return None
    value = payload.get(key)
    return value if isinstance(value, Mapping) else None


def _list_value(payload: Mapping[str, object] | None, key: str) -> list[object]:
    if payload is None:
        return []
    value = payload.get(key)
    return value if isinstance(value, list) else []


def _list_of_mappings(payload: Mapping[str, object] | None, key: str) -> tuple[Mapping[str, object], ...]:
    return tuple(value for value in _list_value(payload, key) if isinstance(value, Mapping))


def _string_list_value(payload: Mapping[str, object] | None, key: str) -> list[str]:
    return [value for value in _list_value(payload, key) if isinstance(value, str)]


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _normalize_required_text(value: str, field_name: str) -> str:
    value = value.strip()
    if not value:
        raise DeploymentReleaseChannelProviderPreflightError(f"{field_name} cannot be empty.")
    return value


def _normalize_text_sequence(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    normalized = tuple(value.strip() for value in values if value.strip())
    if not normalized:
        raise DeploymentReleaseChannelProviderPreflightError(f"{field_name} must include at least one item.")
    return normalized


def _normalize_created_at(value: str | None) -> str:
    if value is not None:
        value = value.strip()
        if not value:
            raise DeploymentReleaseChannelProviderPreflightError("created_at cannot be empty.")
        return value
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
