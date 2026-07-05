from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.vyu.deployment.release_channel_provider_preflight import DEPLOYMENT_RELEASE_CHANNEL_PROVIDER_PREFLIGHT_SCHEMA

DEPLOYMENT_RELEASE_CHANNEL_PROVIDER_DECISION_SCHEMA = 1
DEPLOYMENT_RELEASE_CHANNEL_PROVIDER_DECISIONS = ("proceed", "block", "defer")
DEFAULT_RELEASE_CHANNEL_PROVIDER_DECISION_NEXT_ACTIONS = (
    "Use this local provider-planning decision as the input to a future provider-plan drafting module.",
    "Keep the selected target family abstract until a later module explicitly introduces provider-specific planning details.",
    "Do not add credentials, provider configuration, cloud SDK calls, artifact transfer, signing, CI upload, scanning, persistence, or deployment from this decision record.",
    "Keep the provider preflight, target decision, release evidence, package evidence, and this decision record together.",
)


class DeploymentReleaseChannelProviderDecisionError(RuntimeError):
    """Raised when release-channel provider-planning decision metadata is invalid."""


@dataclass(frozen=True)
class DeploymentReleaseChannelProviderDecisionCheck:
    name: str
    passed: bool
    detail: str

    def to_json(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class DeploymentReleaseChannelProviderPreflightInput:
    path: Path
    sha256: str | None
    readable: bool
    json_valid: bool
    schema_version: int | None
    status: str | None
    created_at: str | None
    preflight_name: str | None

    def to_json(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "readable": self.readable,
            "json_valid": self.json_valid,
            "schema_version": self.schema_version,
            "status": self.status,
            "created_at": self.created_at,
            "preflight_name": self.preflight_name,
        }


@dataclass(frozen=True)
class DeploymentReleaseChannelProviderDecisionRecord:
    decided_at: str
    provider_preflight_path: Path
    provider_preflight: DeploymentReleaseChannelProviderPreflightInput
    operator_id: str
    operator_role: str
    decision: str
    provider_planning_track: str | None
    rationale: str
    planning_decision_scope: str
    selected_target_family: str | None
    selected_target_provider: str | None
    provider_configuration: dict[str, object]
    package: dict[str, object]
    target_operator: dict[str, object]
    inherited_operator: dict[str, object]
    target_decision: dict[str, object]
    target_decision_operator: dict[str, object]
    target_selection_scope: str | None
    candidate_target_families: tuple[str, ...]
    export_summary: dict[str, object]
    evidence_hashes: dict[str, object]
    evidence_counts: dict[str, object]
    local_only_limits: tuple[str, ...]
    handoff_checklist: tuple[str, ...]
    planning_requirements: tuple[str, ...]
    next_actions: tuple[str, ...]
    checks: tuple[DeploymentReleaseChannelProviderDecisionCheck, ...] = field(default_factory=tuple)

    @property
    def status(self) -> str:
        if self.decision == "proceed" and all(check.passed for check in self.checks):
            return "approved"
        if self.decision == "defer" and all(check.passed for check in self.checks):
            return "deferred"
        return "blocked"

    @property
    def decision_id(self) -> str:
        hash_prefix = (self.provider_preflight.sha256 or "missing-preflight")[:12]
        track = self.provider_planning_track or "no-track"
        return "deployment-release-channel-provider-{hash}-{decision}-{track}-{operator}".format(
            hash=hash_prefix,
            decision=_safe_token(self.decision),
            track=_safe_token(track),
            operator=_safe_token(self.operator_id),
        )

    @property
    def blocking_reasons(self) -> tuple[str, ...]:
        reasons: list[str] = []
        if self.decision == "block":
            reasons.append("operator_decision_block")
        for check in self.checks:
            if not check.passed:
                reasons.append(check.name)
        return tuple(sorted(set(reasons)))

    def to_json(self) -> dict[str, object]:
        passed = sum(1 for check in self.checks if check.passed)
        failed = len(self.checks) - passed
        return {
            "schema_version": DEPLOYMENT_RELEASE_CHANNEL_PROVIDER_DECISION_SCHEMA,
            "status": self.status,
            "decision_id": self.decision_id,
            "decided_at": self.decided_at,
            "provider_preflight_path": str(self.provider_preflight_path),
            "provider_preflight": self.provider_preflight.to_json(),
            "package": dict(self.package),
            "target_operator": dict(self.target_operator),
            "inherited_operator": dict(self.inherited_operator),
            "target_decision": dict(self.target_decision),
            "target_decision_operator": dict(self.target_decision_operator),
            "operator": {"id": self.operator_id, "role": self.operator_role},
            "decision": {
                "value": self.decision,
                "provider_planning_track": self.provider_planning_track,
                "rationale": self.rationale,
            },
            "planning_decision_scope": self.planning_decision_scope,
            "selected_target_family": self.selected_target_family,
            "selected_target_provider": self.selected_target_provider,
            "provider_configuration": dict(self.provider_configuration),
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
                "local_only_limit_count": len(self.local_only_limits),
                "next_action_count": len(self.next_actions),
            },
            "checks": [check.to_json() for check in self.checks],
        }


def build_deployment_release_channel_provider_decision_record(
    *,
    provider_preflight_path: Path,
    decision: str,
    operator_id: str,
    operator_role: str,
    rationale: str,
    provider_planning_track: str | None = None,
    decided_at: str | None = None,
    root: Path = Path("."),
    next_actions: Sequence[str] = DEFAULT_RELEASE_CHANNEL_PROVIDER_DECISION_NEXT_ACTIONS,
) -> DeploymentReleaseChannelProviderDecisionRecord:
    """Build a local operator decision for proceeding to provider planning without provider configuration."""

    decision = _normalize_required_value("decision", decision)
    if decision not in DEPLOYMENT_RELEASE_CHANNEL_PROVIDER_DECISIONS:
        raise DeploymentReleaseChannelProviderDecisionError(
            f"Unsupported deployment release-channel provider-planning decision: {decision}."
        )
    operator_id = _normalize_required_value("operator_id", operator_id)
    operator_role = _normalize_required_value("operator_role", operator_role)
    rationale = _normalize_required_value("rationale", rationale)
    provider_planning_track = _normalize_optional_text(provider_planning_track)
    decided_at = _normalize_decided_at(decided_at)
    normalized_next_actions = _normalize_text_sequence(next_actions, "next_actions")

    root = Path(root)
    provider_preflight_path = Path(provider_preflight_path)
    payload, preflight = _read_provider_preflight(provider_preflight_path, root=root)
    provider_configuration = dict(_mapping_value(payload, "provider_configuration") or {})
    checks = _build_checks(
        payload=payload,
        preflight=preflight,
        decision=decision,
        operator_id=operator_id,
        operator_role=operator_role,
        rationale=rationale,
        provider_planning_track=provider_planning_track,
        provider_configuration=provider_configuration,
        next_actions=normalized_next_actions,
    )

    return DeploymentReleaseChannelProviderDecisionRecord(
        decided_at=decided_at,
        provider_preflight_path=provider_preflight_path,
        provider_preflight=preflight,
        operator_id=operator_id,
        operator_role=operator_role,
        decision=decision,
        provider_planning_track=provider_planning_track,
        rationale=rationale,
        planning_decision_scope="local_provider_planning_decision_only",
        selected_target_family=_str_or_none(payload.get("selected_target_family") if payload else None),
        selected_target_provider=_str_or_none(payload.get("selected_target_provider") if payload else None),
        provider_configuration=provider_configuration,
        package=dict(_mapping_value(payload, "package") or {}),
        target_operator=dict(_mapping_value(payload, "target_operator") or {}),
        inherited_operator=dict(_mapping_value(payload, "inherited_operator") or {}),
        target_decision=dict(_mapping_value(payload, "target_decision") or {}),
        target_decision_operator=dict(_mapping_value(payload, "decision") or {}),
        target_selection_scope=_str_or_none(payload.get("target_selection_scope") if payload else None),
        candidate_target_families=tuple(_string_list_value(payload, "candidate_target_families")),
        export_summary=dict(_mapping_value(payload, "export_summary") or {}),
        evidence_hashes=dict(_mapping_value(payload, "evidence_hashes") or {}),
        evidence_counts=dict(_mapping_value(payload, "evidence_counts") or {}),
        local_only_limits=tuple(_string_list_value(payload, "local_only_limits")),
        handoff_checklist=tuple(_string_list_value(payload, "handoff_checklist")),
        planning_requirements=tuple(_string_list_value(payload, "planning_requirements")),
        next_actions=normalized_next_actions,
        checks=checks,
    )


def write_deployment_release_channel_provider_decision_record(
    record: DeploymentReleaseChannelProviderDecisionRecord,
    output_path: Path,
) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(record.to_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _build_checks(
    *,
    payload: Mapping[str, object] | None,
    preflight: DeploymentReleaseChannelProviderPreflightInput,
    decision: str,
    operator_id: str,
    operator_role: str,
    rationale: str,
    provider_planning_track: str | None,
    provider_configuration: Mapping[str, object],
    next_actions: tuple[str, ...],
) -> tuple[DeploymentReleaseChannelProviderDecisionCheck, ...]:
    preflight_checks = _list_of_mappings(payload, "checks")
    failed_preflight_checks = [
        _str_or_none(check.get("name")) or "unnamed_check"
        for check in preflight_checks
        if check.get("passed") is not True
    ]
    preflight_blocking_reasons = _string_list_value(payload, "blocking_reasons")
    evidence_hashes = _mapping_value(payload, "evidence_hashes")
    selected_target_family = _str_or_none(payload.get("selected_target_family") if payload else None)
    return (
        DeploymentReleaseChannelProviderDecisionCheck(
            "provider_preflight_file_readable",
            preflight.readable,
            str(preflight.path),
        ),
        DeploymentReleaseChannelProviderDecisionCheck(
            "provider_preflight_json_valid",
            preflight.json_valid,
            "valid" if preflight.json_valid else "invalid",
        ),
        DeploymentReleaseChannelProviderDecisionCheck(
            "provider_preflight_schema_supported",
            preflight.schema_version == DEPLOYMENT_RELEASE_CHANNEL_PROVIDER_PREFLIGHT_SCHEMA,
            f"schema_version={preflight.schema_version}",
        ),
        DeploymentReleaseChannelProviderDecisionCheck(
            "provider_preflight_status_ready",
            preflight.status == "ready",
            str(preflight.status),
        ),
        DeploymentReleaseChannelProviderDecisionCheck(
            "provider_preflight_checks_passed",
            len(preflight_checks) > 0 and len(failed_preflight_checks) == 0,
            "failed=" + ",".join(failed_preflight_checks) if failed_preflight_checks else f"checks={len(preflight_checks)}",
        ),
        DeploymentReleaseChannelProviderDecisionCheck(
            "provider_preflight_blocking_reasons_absent",
            len(preflight_blocking_reasons) == 0,
            f"count={len(preflight_blocking_reasons)}",
        ),
        DeploymentReleaseChannelProviderDecisionCheck(
            "decision_supported",
            decision in DEPLOYMENT_RELEASE_CHANNEL_PROVIDER_DECISIONS,
            decision,
        ),
        DeploymentReleaseChannelProviderDecisionCheck(
            "operator_metadata_present",
            bool(operator_id and operator_role and rationale),
            "operator_id,operator_role,rationale",
        ),
        DeploymentReleaseChannelProviderDecisionCheck(
            "proceed_requires_ready_preflight",
            decision != "proceed" or preflight.status == "ready",
            f"decision={decision},provider_preflight_status={preflight.status}",
        ),
        DeploymentReleaseChannelProviderDecisionCheck(
            "proceed_requires_provider_planning_track",
            decision != "proceed" or bool(provider_planning_track),
            f"decision={decision},provider_planning_track={provider_planning_track}",
        ),
        DeploymentReleaseChannelProviderDecisionCheck(
            "block_or_defer_requires_no_provider_planning_track",
            decision == "proceed" or provider_planning_track is None,
            f"decision={decision},provider_planning_track={provider_planning_track}",
        ),
        DeploymentReleaseChannelProviderDecisionCheck(
            "selected_target_family_present",
            bool(selected_target_family),
            str(selected_target_family),
        ),
        DeploymentReleaseChannelProviderDecisionCheck(
            "planning_scope_preflight_only",
            _str_or_none(payload.get("planning_scope") if payload else None) == "provider_planning_preflight_only",
            str(payload.get("planning_scope") if payload else None),
        ),
        DeploymentReleaseChannelProviderDecisionCheck(
            "target_selection_scope_local_only",
            _str_or_none(payload.get("target_selection_scope") if payload else None) == "local_target_family_review_only",
            str(payload.get("target_selection_scope") if payload else None),
        ),
        DeploymentReleaseChannelProviderDecisionCheck(
            "no_target_provider_selected",
            _str_or_none(payload.get("selected_target_provider") if payload else None) is None,
            "selected_target_provider=None",
        ),
        DeploymentReleaseChannelProviderDecisionCheck(
            "no_provider_configuration_recorded",
            len(provider_configuration) == 0,
            f"keys={len(provider_configuration)}",
        ),
        DeploymentReleaseChannelProviderDecisionCheck(
            "export_summary_sha256_present",
            bool(_nested_str(payload, "export_summary", "sha256")),
            "export_summary.sha256",
        ),
        DeploymentReleaseChannelProviderDecisionCheck(
            "evidence_index_sha256_present",
            bool(_str_or_none(evidence_hashes.get("evidence_index_sha256") if evidence_hashes else None)),
            "evidence_hashes.evidence_index_sha256",
        ),
        DeploymentReleaseChannelProviderDecisionCheck(
            "package_metadata_present",
            _package_metadata_present(_mapping_value(payload, "package")),
            "package_name,runtime,handler",
        ),
        DeploymentReleaseChannelProviderDecisionCheck(
            "target_operator_metadata_present",
            _operator_metadata_present(_mapping_value(payload, "target_operator")),
            "target_operator.id,target_operator.role",
        ),
        DeploymentReleaseChannelProviderDecisionCheck(
            "local_only_limits_present",
            len(_string_list_value(payload, "local_only_limits")) > 0,
            f"count={len(_string_list_value(payload, 'local_only_limits'))}",
        ),
        DeploymentReleaseChannelProviderDecisionCheck(
            "handoff_checklist_present",
            len(_string_list_value(payload, "handoff_checklist")) > 0,
            f"count={len(_string_list_value(payload, 'handoff_checklist'))}",
        ),
        DeploymentReleaseChannelProviderDecisionCheck(
            "planning_requirements_present",
            len(_string_list_value(payload, "planning_requirements")) > 0,
            f"count={len(_string_list_value(payload, 'planning_requirements'))}",
        ),
        DeploymentReleaseChannelProviderDecisionCheck(
            "next_actions_present",
            len(next_actions) > 0,
            f"count={len(next_actions)}",
        ),
    )


def _read_provider_preflight(
    path: Path,
    *,
    root: Path,
) -> tuple[Mapping[str, object] | None, DeploymentReleaseChannelProviderPreflightInput]:
    path = Path(path)
    file_path = path if path.is_absolute() else root / path
    sha256 = _sha256(file_path) if file_path.is_file() else None
    if not file_path.is_file():
        return None, DeploymentReleaseChannelProviderPreflightInput(
            path=path,
            sha256=None,
            readable=False,
            json_valid=False,
            schema_version=None,
            status=None,
            created_at=None,
            preflight_name=None,
        )
    try:
        payload: Any = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, DeploymentReleaseChannelProviderPreflightInput(
            path=path,
            sha256=sha256,
            readable=True,
            json_valid=False,
            schema_version=None,
            status=None,
            created_at=None,
            preflight_name=None,
        )
    if not isinstance(payload, Mapping):
        return None, DeploymentReleaseChannelProviderPreflightInput(
            path=path,
            sha256=sha256,
            readable=True,
            json_valid=False,
            schema_version=None,
            status=None,
            created_at=None,
            preflight_name=None,
        )
    return payload, DeploymentReleaseChannelProviderPreflightInput(
        path=path,
        sha256=sha256,
        readable=True,
        json_valid=True,
        schema_version=_optional_int(payload.get("schema_version")),
        status=_str_or_none(payload.get("status")),
        created_at=_str_or_none(payload.get("created_at")),
        preflight_name=_str_or_none(payload.get("preflight_name")),
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


def _normalize_required_value(field_name: str, value: str) -> str:
    value = value.strip()
    if not value:
        raise DeploymentReleaseChannelProviderDecisionError(f"{field_name} cannot be empty.")
    return value


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _normalize_text_sequence(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    normalized = tuple(value.strip() for value in values if value.strip())
    if not normalized:
        raise DeploymentReleaseChannelProviderDecisionError(f"{field_name} must include at least one item.")
    return normalized


def _normalize_decided_at(value: str | None) -> str:
    if value is not None:
        value = value.strip()
        if not value:
            raise DeploymentReleaseChannelProviderDecisionError("decided_at cannot be empty.")
        return value
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_token(value: str) -> str:
    return "-".join(part for part in value.lower().replace("_", "-").split() if part) or "unknown"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
