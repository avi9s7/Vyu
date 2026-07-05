from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Mapping, Sequence

from src.vyu.deployment.command_transcript import DEPLOYMENT_COMMAND_TRANSCRIPT_SCHEMA
from src.vyu.deployment.package_manifest import (
    DeploymentPackageManifestError,
    read_deployment_package_manifest,
)

DEPLOYMENT_TRANSCRIPT_BUNDLE_SCHEMA = 1


class DeploymentTranscriptBundleError(RuntimeError):
    """Raised when a deployment transcript bundle cannot be produced."""


@dataclass(frozen=True)
class DeploymentTranscriptBundleCheck:
    name: str
    passed: bool
    detail: str

    def to_json(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class DeploymentTranscriptSummary:
    path: Path
    status: str
    schema_version: int | None
    purpose: str | None
    command: tuple[str, ...] | None
    exit_code: int | None
    started_at: str | None
    finished_at: str | None
    artifact_summary: dict[str, int]
    checks: tuple[DeploymentTranscriptBundleCheck, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def command_key(self) -> str | None:
        if self.command is None:
            return None
        return _command_key(self.command)

    def to_json(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "status": self.status,
            "schema_version": self.schema_version,
            "purpose": self.purpose,
            "command": list(self.command) if self.command is not None else None,
            "exit_code": self.exit_code,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "artifact_summary": dict(self.artifact_summary),
            "checks": [check.to_json() for check in self.checks],
        }


@dataclass(frozen=True)
class DeploymentTranscriptBundle:
    created_at: str
    manifest_path: Path
    transcript_paths: tuple[Path, ...]
    required_commands: tuple[tuple[str, ...], ...]
    command_coverage: dict[str, bool]
    transcript_summaries: tuple[DeploymentTranscriptSummary, ...]
    checks: tuple[DeploymentTranscriptBundleCheck, ...] = field(default_factory=tuple)

    @property
    def status(self) -> str:
        return "ready" if all(check.passed for check in self.checks) else "blocked"

    def to_json(self) -> dict[str, object]:
        passed = sum(1 for check in self.checks if check.passed)
        failed = len(self.checks) - passed
        covered = sum(1 for covered in self.command_coverage.values() if covered)
        path_by_command = _passed_transcript_path_by_command(self.transcript_summaries)
        return {
            "schema_version": DEPLOYMENT_TRANSCRIPT_BUNDLE_SCHEMA,
            "status": self.status,
            "created_at": self.created_at,
            "manifest_path": str(self.manifest_path),
            "transcript_paths": [str(path) for path in self.transcript_paths],
            "required_commands": [
                {
                    "index": index,
                    "command": list(command),
                    "covered": self.command_coverage[_command_key(command)],
                    "transcript_path": str(path_by_command[_command_key(command)])
                    if _command_key(command) in path_by_command
                    else None,
                }
                for index, command in enumerate(self.required_commands)
            ],
            "command_coverage": dict(self.command_coverage),
            "transcripts": [summary.to_json() for summary in self.transcript_summaries],
            "summary": {
                "passed": passed,
                "failed": failed,
                "total": len(self.checks),
                "transcript_count": len(self.transcript_summaries),
                "required_command_count": len(self.required_commands),
                "covered_command_count": covered,
            },
            "checks": [check.to_json() for check in self.checks],
        }


def build_deployment_transcript_bundle(
    manifest_path: Path,
    *,
    transcript_paths: Sequence[Path],
    root: Path = Path("."),
    created_at: str | None = None,
) -> DeploymentTranscriptBundle:
    """Build a local readiness bundle from pre-written command transcript JSON files."""

    manifest_path = Path(manifest_path)
    root = Path(root)
    transcript_paths = tuple(Path(path) for path in transcript_paths)
    created_at = _normalize_created_at(created_at)

    try:
        manifest = read_deployment_package_manifest(manifest_path)
    except DeploymentPackageManifestError as exc:
        raise DeploymentTranscriptBundleError(str(exc)) from exc

    transcript_summaries = tuple(_summarize_transcript(path, root=root) for path in transcript_paths)
    command_coverage = _command_coverage(manifest.required_validation_commands, transcript_summaries)
    checks = _bundle_checks(
        transcript_paths=transcript_paths,
        required_commands=manifest.required_validation_commands,
        command_coverage=command_coverage,
        transcript_summaries=transcript_summaries,
    )

    return DeploymentTranscriptBundle(
        created_at=created_at,
        manifest_path=manifest_path,
        transcript_paths=transcript_paths,
        required_commands=manifest.required_validation_commands,
        command_coverage=command_coverage,
        transcript_summaries=transcript_summaries,
        checks=checks,
    )


def write_deployment_transcript_bundle(bundle: DeploymentTranscriptBundle, output_path: Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(bundle.to_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _normalize_created_at(value: str | None) -> str:
    if value is not None:
        value = value.strip()
        if not value:
            raise DeploymentTranscriptBundleError("created_at cannot be empty.")
        return value
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _summarize_transcript(path: Path, *, root: Path) -> DeploymentTranscriptSummary:
    absolute = root / path
    if not absolute.is_file():
        return DeploymentTranscriptSummary(
            path=path,
            status="missing",
            schema_version=None,
            purpose=None,
            command=None,
            exit_code=None,
            started_at=None,
            finished_at=None,
            artifact_summary=_empty_artifact_summary(),
            checks=(
                DeploymentTranscriptBundleCheck("transcript_file_exists", False, str(path)),
            ),
        )

    try:
        payload = json.loads(absolute.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return DeploymentTranscriptSummary(
            path=path,
            status="invalid",
            schema_version=None,
            purpose=None,
            command=None,
            exit_code=None,
            started_at=None,
            finished_at=None,
            artifact_summary=_empty_artifact_summary(),
            checks=(
                DeploymentTranscriptBundleCheck("transcript_file_exists", True, str(path)),
                DeploymentTranscriptBundleCheck("transcript_json_valid", False, str(exc)),
            ),
        )
    if not isinstance(payload, Mapping):
        return DeploymentTranscriptSummary(
            path=path,
            status="invalid",
            schema_version=None,
            purpose=None,
            command=None,
            exit_code=None,
            started_at=None,
            finished_at=None,
            artifact_summary=_empty_artifact_summary(),
            checks=(
                DeploymentTranscriptBundleCheck("transcript_file_exists", True, str(path)),
                DeploymentTranscriptBundleCheck("transcript_json_object", False, "not an object"),
            ),
        )

    schema_version = _optional_int(payload.get("schema_version"))
    status = str(payload.get("status", "invalid"))
    purpose = payload.get("purpose") if isinstance(payload.get("purpose"), str) else None
    command = _command_from_payload(payload.get("command"))
    exit_code = _optional_int(payload.get("exit_code"))
    started_at = payload.get("started_at") if isinstance(payload.get("started_at"), str) else None
    finished_at = payload.get("finished_at") if isinstance(payload.get("finished_at"), str) else None
    artifact_summary = _artifact_summary(payload.get("artifacts"))
    checks = _transcript_checks(
        path=path,
        schema_version=schema_version,
        status=status,
        command=command,
        exit_code=exit_code,
        started_at=started_at,
        finished_at=finished_at,
        outputs=payload.get("outputs"),
        artifact_summary=artifact_summary,
    )
    return DeploymentTranscriptSummary(
        path=path,
        status=status,
        schema_version=schema_version,
        purpose=purpose,
        command=command,
        exit_code=exit_code,
        started_at=started_at,
        finished_at=finished_at,
        artifact_summary=artifact_summary,
        checks=checks,
    )


def _transcript_checks(
    *,
    path: Path,
    schema_version: int | None,
    status: str,
    command: tuple[str, ...] | None,
    exit_code: int | None,
    started_at: str | None,
    finished_at: str | None,
    outputs: object,
    artifact_summary: Mapping[str, int],
) -> tuple[DeploymentTranscriptBundleCheck, ...]:
    return (
        DeploymentTranscriptBundleCheck("transcript_file_exists", True, str(path)),
        DeploymentTranscriptBundleCheck(
            "transcript_schema_supported",
            schema_version == DEPLOYMENT_COMMAND_TRANSCRIPT_SCHEMA,
            f"schema_version={schema_version}",
        ),
        DeploymentTranscriptBundleCheck("transcript_status_passed", status == "passed", status),
        DeploymentTranscriptBundleCheck("transcript_exit_code_zero", exit_code == 0, f"exit_code={exit_code}"),
        DeploymentTranscriptBundleCheck("transcript_command_valid", command is not None, _command_key(command or ())),
        DeploymentTranscriptBundleCheck("transcript_started_at_present", bool(started_at), str(started_at)),
        DeploymentTranscriptBundleCheck("transcript_finished_at_present", bool(finished_at), str(finished_at)),
        DeploymentTranscriptBundleCheck(
            "transcript_outputs_hashed",
            _outputs_have_hashes(outputs),
            "stdout/stderr sha256",
        ),
        DeploymentTranscriptBundleCheck(
            "recorded_artifacts_exist_and_hashed",
            artifact_summary["missing"] == 0 and artifact_summary["unhashed_existing"] == 0,
            "missing={missing}, unhashed_existing={unhashed_existing}".format(**artifact_summary),
        ),
    )


def _bundle_checks(
    *,
    transcript_paths: Sequence[Path],
    required_commands: Sequence[Sequence[str]],
    command_coverage: Mapping[str, bool],
    transcript_summaries: Sequence[DeploymentTranscriptSummary],
) -> tuple[DeploymentTranscriptBundleCheck, ...]:
    per_transcript_failed = sum(1 for summary in transcript_summaries if not summary.passed)
    missing_commands = [key for key, covered in command_coverage.items() if not covered]
    return (
        DeploymentTranscriptBundleCheck(
            "transcripts_provided",
            len(transcript_paths) > 0,
            str(len(transcript_paths)),
        ),
        DeploymentTranscriptBundleCheck(
            "all_transcripts_valid_and_passed",
            per_transcript_failed == 0,
            f"failed={per_transcript_failed}",
        ),
        DeploymentTranscriptBundleCheck(
            "required_command_coverage_complete",
            all(command_coverage.values()),
            "missing=" + ",".join(missing_commands) if missing_commands else "complete",
        ),
        DeploymentTranscriptBundleCheck(
            "required_command_sequence_order",
            _required_sequence_ordered(required_commands, transcript_summaries),
            "manifest order",
        ),
    )


def _command_coverage(
    required_commands: Sequence[Sequence[str]],
    summaries: Sequence[DeploymentTranscriptSummary],
) -> dict[str, bool]:
    passed_commands = {
        summary.command_key()
        for summary in summaries
        if summary.command is not None and summary.status == "passed" and summary.exit_code == 0 and summary.passed
    }
    return {_command_key(command): _command_key(command) in passed_commands for command in required_commands}


def _required_sequence_ordered(
    required_commands: Sequence[Sequence[str]],
    summaries: Sequence[DeploymentTranscriptSummary],
) -> bool:
    required_keys = [_command_key(command) for command in required_commands]
    if not required_keys:
        return True
    cursor = 0
    seen: list[str] = []
    for summary in summaries:
        key = summary.command_key()
        if key is None or summary.status != "passed" or not summary.passed:
            continue
        if cursor < len(required_keys) and key == required_keys[cursor]:
            seen.append(key)
            cursor += 1
    return seen == required_keys


def _passed_transcript_path_by_command(
    summaries: Sequence[DeploymentTranscriptSummary],
) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for summary in summaries:
        key = summary.command_key()
        if key is not None and summary.status == "passed" and summary.passed and key not in paths:
            paths[key] = summary.path
    return paths


def _command_from_payload(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    if any(not isinstance(part, str) or not part.strip() for part in value):
        return None
    return tuple(value)


def _outputs_have_hashes(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    return _output_hash_valid(value.get("stdout")) and _output_hash_valid(value.get("stderr"))


def _output_hash_valid(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    sha256 = value.get("sha256")
    length = value.get("length_bytes")
    return isinstance(sha256, str) and _is_sha256(sha256) and isinstance(length, int) and length >= 0


def _artifact_summary(value: object) -> dict[str, int]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return _empty_artifact_summary()
    total = 0
    existing = 0
    missing = 0
    hashed = 0
    unhashed_existing = 0
    for artifact in value:
        if not isinstance(artifact, Mapping):
            missing += 1
            total += 1
            continue
        total += 1
        exists = artifact.get("exists") is True
        sha256 = artifact.get("sha256")
        if exists:
            existing += 1
            if isinstance(sha256, str) and _is_sha256(sha256):
                hashed += 1
            else:
                unhashed_existing += 1
        else:
            missing += 1
    return {
        "total": total,
        "existing": existing,
        "missing": missing,
        "hashed": hashed,
        "unhashed_existing": unhashed_existing,
    }


def _empty_artifact_summary() -> dict[str, int]:
    return {"total": 0, "existing": 0, "missing": 0, "hashed": 0, "unhashed_existing": 0}


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _command_key(command: Sequence[str]) -> str:
    return " ".join(command)
