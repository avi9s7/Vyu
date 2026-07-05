from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.vyu.deployment.release_channel_target import DEPLOYMENT_RELEASE_CHANNEL_TARGET_READINESS_SCHEMA

DEPLOYMENT_RELEASE_CHANNEL_TARGET_DECISION_SCHEMA = 1
DEPLOYMENT_RELEASE_CHANNEL_TARGET_DECISIONS = ("choose", "block", "defer")
DEFAULT_RELEASE_CHANNEL_TARGET_DECISION_NEXT_ACTIONS = (
    "Use this abstract target-family decision as the input to a future provider-specific planning module.",
    "Do not add provider configuration until the selected target family has been reviewed explicitly.",
    "Keep release evidence, package evidence, export summary, target-readiness note, and this decision record together.",
    "Do not transfer, sign, upload, scan, persist to production storage, or deploy artifacts from this local decision record.",
)


class DeploymentReleaseChannelTargetDecisionError(RuntimeError):
    """Raised when release-channel target-decision metadata is invalid."""


@dataclass(frozen=True)
class DeploymentReleaseChannelTargetDecisionCheck:
    name: str
    passed: bool
    detail: str

    def to_json(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class DeploymentReleaseChannelTargetReadinessInput:
    path: Path
    sha256: str | None
    readable: bool
    json_valid: bool
    schema_version: int | None
    status: str | None
    created_at: str | None
    readiness_name: str | None

    def to_json(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "readable": self.readable,
            "json_valid": self.json_valid,
            "schema_version": self.schema_version,
            "status": self.status,
            "created_at": self.created_at,
            "readiness_name": self.readiness_name,
        }


@dataclass(frozen=True)
class DeploymentReleaseChannelTargetDecisionRecord:
    decided_at: str
    target_readiness_path: Path
    target_readiness: DeploymentReleaseChannelTargetReadinessInput
    operator_id: str
    operator_role: str
    decision: str
    selected_target_family: str | None
    rationale: str
    package: dict[str, object]
    inherited_operator: dict[str, object]
    target_selection_scope: str | None
    candidate_target_families: tuple[str, ...]
    selected_target_provider: str | None
    provider_configuration: dict[str, object]
    export_summary: dict[str, object]
    evidence_hashes: dict[str, object]
    evidence_counts: dict[str, object]
    local_only_limits: tuple[str, ...]
    handoff_checklist: tuple[str, ...]
    next_actions: tuple[str, ...]
    checks: tuple[DeploymentReleaseChannelTargetDecisionCheck, ...] = field(default_factory=tuple)

    @property
    def status(self) -> str:
        if self.decision == "choose" and all(check.passed for check in self.checks):
            return "selected"
        if self.decision == "defer" and all(check.passed for check in self.checks):
            return "deferred"
        return "blocked"

    @property
    def decision_id(self) -> str:
        hash_prefix = (self.target_readiness.sha256 or "missing-readiness")[:12]
        family = self.selected_target_family or "no-family"
        return "deployment-release-channel-target-{hash}-{decision}-{family}-{operator}".format(
            hash=hash_prefix,
            decision=_safe_token(self.decision),
            family=_safe_token(family),
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
            "schema_version": DEPLOYMENT_RELEASE_CHANNEL_TARGET_DECISION_SCHEMA,
            "status": self.status,
            "decision_id": self.decision_id,
            "decided_at": self.decided_at,
            "target_readiness_path": str(self.target_readiness_path),
            "target_readiness": self.target_readiness.to_json(),
            "package": dict(self.package),
            "inherited_operator": dict(self.inherited_operator),
            "operator": {"id": self.operator_id, "role": self.operator_role},
            "decision": {
                "value": self.decision,
                "selected_target_family": self.selected_target_family,
                "rationale": self.rationale,
            },
            "target_selection_scope": self.target_selection_scope,
            "candidate_target_families": list(self.candidate_target_families),
            "selected_target_provider": self.selected_target_provider,
            "provider_configuration": dict(self.provider_configuration),
            "export_summary": dict(self.export_summary),
            "evidence_hashes": dict(self.evidence_hashes),
            "evidence_counts": dict(self.evidence_counts),
            "local_only_limits": list(self.local_only_limits),
            "handoff_checklist": list(self.handoff_checklist),
            "next_actions": list(self.next_actions),
            "blocking_reasons": list(self.blocking_reasons),
            "summary": {
                "passed": passed,
                "failed": failed,
                "total": len(self.checks),
                "candidate_target_family_count": len(self.candidate_target_families),
                "local_only_limit_count": len(self.local_only_limits),
                "next_action_count": len(self.next_actions),
            },
            "checks": [check.to_json() for check in self.checks],
        }


def build_deployment_release_channel_target_decision_record(
    *,
    target_readiness_path: Path,
    decision: str,
    operator_id: str,
    operator_role: str,
    rationale: str,
    selected_target_family: str | None = None,
    decided_at: str | None = None,
    root: Path = Path("."),
    next_actions: Sequence[str] = DEFAULT_RELEASE_CHANNEL_TARGET_DECISION_NEXT_ACTIONS,
) -> DeploymentReleaseChannelTargetDecisionRecord:
    """Build a local operator target-family decision bound to a target-readiness SHA-256."""

    decision = _normalize_required_value("decision", decision)
    if decision not in DEPLOYMENT_RELEASE_CHANNEL_TARGET_DECISIONS:
        raise DeploymentReleaseChannelTargetDecisionError(
            f"Unsupported deployment release-channel target decision: {decision}."
        )
    operator_id = _normalize_required_value("operator_id", operator_id)
    operator_role = _normalize_required_value("operator_role", operator_role)
    rationale = _normalize_required_value("rationale", rationale)
    selected_target_family = _normalize_optional_text(selected_target_family)
    decided_at = _normalize_decided_at(decided_at)
    normalized_next_actions = _normalize_text_sequence(next_actions, "next_actions")

    root = Path(root)
    target_readiness_path = Path(target_readiness_path)
    payload, readiness = _read_target_readiness(target_readiness_path, root=root)
    candidate_target_families = tuple(_string_list_value(payload, "candidate_target_families"))
    provider_configuration = dict(_mapping_value(payload, "provider_configuration") or {})
    checks = _build_checks(
        payload=payload,
        readiness=readiness,
        decision=decision,
        selected_target_family=selected_target_family,
        operator_id=operator_id,
        operator_role=operator_role,
        rationale=rationale,
        candidate_target_families=candidate_target_families,
        provider_configuration=provider_configuration,
        next_actions=normalized_next_actions,
    )

    return DeploymentReleaseChannelTargetDecisionRecord(
        decided_at=decided_at,
        target_readiness_path=target_readiness_path,
        target_readiness=readiness,
        operator_id=operator_id,
        operator_role=operator_role,
        decision=decision,
        selected_target_family=selected_target_family,
        rationale=rationale,
        package=dict(_mapping_value(payload, "package") or {}),
        inherited_operator=dict(_mapping_value(payload, "operator") or {}),
        target_selection_scope=_str_or_none(payload.get("target_selection_scope") if payload else None),
        candidate_target_families=candidate_target_families,
        selected_target_provider=_str_or_none(payload.get("selected_target_provider") if payload else None),
        provider_configuration=provider_configuration,
        export_summary=dict(_mapping_value(payload, "export_summary") or {}),
        evidence_hashes=dict(_mapping_value(payload, "evidence_hashes") or {}),
        evidence_counts=dict(_mapping_value(payload, "evidence_counts") or {}),
        local_only_limits=tuple(_string_list_value(payload, "local_only_limits")),
        handoff_checklist=tuple(_string_list_value(payload, "handoff_checklist")),
        next_actions=normalized_next_actions,
        checks=checks,
    )


def write_deployment_release_channel_target_decision_record(
    record: DeploymentReleaseChannelTargetDecisionRecord,
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
    readiness: DeploymentReleaseChannelTargetReadinessInput,
    decision: str,
    selected_target_family: str | None,
    operator_id: str,
    operator_role: str,
    rationale: str,
    candidate_target_families: tuple[str, ...],
    provider_configuration: Mapping[str, object],
    next_actions: tuple[str, ...],
) -> tuple[DeploymentReleaseChannelTargetDecisionCheck, ...]:
    readiness_checks = _list_of_mappings(payload, "checks")
    failed_readiness_checks = [
        _str_or_none(check.get("name")) or "unnamed_check"
        for check in readiness_checks
        if check.get("passed") is not True
    ]
    readiness_blocking_reasons = _string_list_value(payload, "blocking_reasons")
    evidence_hashes = _mapping_value(payload, "evidence_hashes")
    return (
        DeploymentReleaseChannelTargetDecisionCheck(
            "target_readiness_file_readable",
            readiness.readable,
            str(readiness.path),
        ),
        DeploymentReleaseChannelTargetDecisionCheck(
            "target_readiness_json_valid",
            readiness.json_valid,
            "valid" if readiness.json_valid else "invalid",
        ),
        DeploymentReleaseChannelTargetDecisionCheck(
            "target_readiness_schema_supported",
            readiness.schema_version == DEPLOYMENT_RELEASE_CHANNEL_TARGET_READINESS_SCHEMA,
            f"schema_version={readiness.schema_version}",
        ),
        DeploymentReleaseChannelTargetDecisionCheck(
            "target_readiness_status_ready",
            readiness.status == "ready",
            str(readiness.status),
        ),
        DeploymentReleaseChannelTargetDecisionCheck(
            "target_readiness_checks_passed",
            len(readiness_checks) > 0 and len(failed_readiness_checks) == 0,
            "failed=" + ",".join(failed_readiness_checks) if failed_readiness_checks else f"checks={len(readiness_checks)}",
        ),
        DeploymentReleaseChannelTargetDecisionCheck(
            "target_readiness_blocking_reasons_absent",
            len(readiness_blocking_reasons) == 0,
            f"count={len(readiness_blocking_reasons)}",
        ),
        DeploymentReleaseChannelTargetDecisionCheck(
            "target_family_candidates_present",
            len(candidate_target_families) > 0,
            f"count={len(candidate_target_families)}",
        ),
        DeploymentReleaseChannelTargetDecisionCheck(
            "decision_supported",
            decision in DEPLOYMENT_RELEASE_CHANNEL_TARGET_DECISIONS,
            decision,
        ),
        DeploymentReleaseChannelTargetDecisionCheck(
            "operator_metadata_present",
            bool(operator_id and operator_role and rationale),
            "operator_id,operator_role,rationale",
        ),
        DeploymentReleaseChannelTargetDecisionCheck(
            "choose_requires_ready_readiness",
            decision != "choose" or readiness.status == "ready",
            f"decision={decision},target_readiness_status={readiness.status}",
        ),
        DeploymentReleaseChannelTargetDecisionCheck(
            "choose_requires_candidate_target_family",
            decision != "choose" or bool(selected_target_family and selected_target_family in candidate_target_families),
            f"selected={selected_target_family},candidates={','.join(candidate_target_families)}",
        ),
        DeploymentReleaseChannelTargetDecisionCheck(
            "block_or_defer_requires_no_selected_target_family",
            decision == "choose" or selected_target_family is None,
            f"decision={decision},selected={selected_target_family}",
        ),
        DeploymentReleaseChannelTargetDecisionCheck(
            "target_selection_scope_local_only",
            _str_or_none(payload.get("target_selection_scope") if payload else None) == "local_target_family_review_only",
            str(payload.get("target_selection_scope") if payload else None),
        ),
        DeploymentReleaseChannelTargetDecisionCheck(
            "no_target_provider_selected",
            _str_or_none(payload.get("selected_target_provider") if payload else None) is None,
            "selected_target_provider=None",
        ),
        DeploymentReleaseChannelTargetDecisionCheck(
            "no_provider_configuration_recorded",
            len(provider_configuration) == 0,
            f"keys={len(provider_configuration)}",
        ),
        DeploymentReleaseChannelTargetDecisionCheck(
            "export_summary_sha256_present",
            bool(_nested_str(payload, "export_summary", "sha256")),
            "export_summary.sha256",
        ),
        DeploymentReleaseChannelTargetDecisionCheck(
            "evidence_index_sha256_present",
            bool(_str_or_none(evidence_hashes.get("evidence_index_sha256") if evidence_hashes else None)),
            "evidence_hashes.evidence_index_sha256",
        ),
        DeploymentReleaseChannelTargetDecisionCheck(
            "package_metadata_present",
            _package_metadata_present(_mapping_value(payload, "package")),
            "package_name,runtime,handler",
        ),
        DeploymentReleaseChannelTargetDecisionCheck(
            "local_only_limits_present",
            len(_string_list_value(payload, "local_only_limits")) > 0,
            f"count={len(_string_list_value(payload, 'local_only_limits'))}",
        ),
        DeploymentReleaseChannelTargetDecisionCheck(
            "handoff_checklist_present",
            len(_string_list_value(payload, "handoff_checklist")) > 0,
            f"count={len(_string_list_value(payload, 'handoff_checklist'))}",
        ),
        DeploymentReleaseChannelTargetDecisionCheck(
            "next_actions_present",
            len(next_actions) > 0,
            f"count={len(next_actions)}",
        ),
    )


def _read_target_readiness(
    path: Path,
    *,
    root: Path,
) -> tuple[Mapping[str, object] | None, DeploymentReleaseChannelTargetReadinessInput]:
    path = Path(path)
    file_path = path if path.is_absolute() else root / path
    sha256 = _sha256(file_path) if file_path.is_file() else None
    if not file_path.is_file():
        return None, DeploymentReleaseChannelTargetReadinessInput(
            path=path,
            sha256=None,
            readable=False,
            json_valid=False,
            schema_version=None,
            status=None,
            created_at=None,
            readiness_name=None,
        )
    try:
        payload: Any = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, DeploymentReleaseChannelTargetReadinessInput(
            path=path,
            sha256=sha256,
            readable=True,
            json_valid=False,
            schema_version=None,
            status=None,
            created_at=None,
            readiness_name=None,
        )
    if not isinstance(payload, Mapping):
        return None, DeploymentReleaseChannelTargetReadinessInput(
            path=path,
            sha256=sha256,
            readable=True,
            json_valid=False,
            schema_version=None,
            status=None,
            created_at=None,
            readiness_name=None,
        )
    return payload, DeploymentReleaseChannelTargetReadinessInput(
        path=path,
        sha256=sha256,
        readable=True,
        json_valid=True,
        schema_version=_optional_int(payload.get("schema_version")),
        status=_str_or_none(payload.get("status")),
        created_at=_str_or_none(payload.get("created_at")),
        readiness_name=_str_or_none(payload.get("readiness_name")),
    )


def _nested_str(payload: Mapping[str, object] | None, parent: str, key: str) -> str | None:
    value = _mapping_value(payload, parent)
    return _str_or_none(value.get(key) if value else None)


def _package_metadata_present(package: Mapping[str, object] | None) -> bool:
    if package is None:
        return False
    return all(bool(_str_or_none(package.get(key))) for key in ("package_name", "runtime", "handler"))


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
        raise DeploymentReleaseChannelTargetDecisionError(f"{field_name} cannot be empty.")
    return value


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _normalize_text_sequence(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    normalized = tuple(value.strip() for value in values if value.strip())
    if not normalized:
        raise DeploymentReleaseChannelTargetDecisionError(f"{field_name} must include at least one item.")
    return normalized


def _normalize_decided_at(value: str | None) -> str:
    if value is not None:
        value = value.strip()
        if not value:
            raise DeploymentReleaseChannelTargetDecisionError("decided_at cannot be empty.")
        return value
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_token(value: str) -> str:
    token = "".join(character if character.isalnum() else "-" for character in value.lower()).strip("-")
    return token or "unknown"
