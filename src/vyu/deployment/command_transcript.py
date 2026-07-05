from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

DEPLOYMENT_COMMAND_TRANSCRIPT_SCHEMA = 1
DEFAULT_OUTPUT_EXCERPT_LIMIT = 240


class DeploymentCommandTranscriptError(RuntimeError):
    """Raised when deployment command transcript evidence cannot be produced."""


@dataclass(frozen=True)
class DeploymentCommandOutput:
    stream: str
    sha256: str
    length_bytes: int
    excerpt: str
    truncated: bool

    def to_json(self) -> dict[str, object]:
        return {
            "stream": self.stream,
            "sha256": self.sha256,
            "length_bytes": self.length_bytes,
            "excerpt": self.excerpt,
            "truncated": self.truncated,
        }


@dataclass(frozen=True)
class DeploymentCommandArtifact:
    path: Path
    exists: bool
    size_bytes: int | None
    sha256: str | None

    def to_json(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "exists": self.exists,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class DeploymentCommandTranscript:
    purpose: str
    command: tuple[str, ...]
    exit_code: int
    started_at: str
    finished_at: str
    stdout: DeploymentCommandOutput
    stderr: DeploymentCommandOutput
    artifacts: tuple[DeploymentCommandArtifact, ...] = field(default_factory=tuple)

    @property
    def status(self) -> str:
        return "passed" if self.exit_code == 0 else "failed"

    def to_json(self) -> dict[str, object]:
        existing_artifacts = sum(1 for artifact in self.artifacts if artifact.exists)
        return {
            "schema_version": DEPLOYMENT_COMMAND_TRANSCRIPT_SCHEMA,
            "status": self.status,
            "purpose": self.purpose,
            "command": list(self.command),
            "exit_code": self.exit_code,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "outputs": {
                "stdout": self.stdout.to_json(),
                "stderr": self.stderr.to_json(),
            },
            "artifacts": [artifact.to_json() for artifact in self.artifacts],
            "summary": {
                "artifact_count": len(self.artifacts),
                "existing_artifact_count": existing_artifacts,
                "missing_artifact_count": len(self.artifacts) - existing_artifacts,
            },
        }


def build_deployment_command_transcript(
    *,
    command: Sequence[str],
    purpose: str,
    exit_code: int,
    started_at: str,
    finished_at: str,
    stdout_text: str = "",
    stderr_text: str = "",
    artifact_paths: Sequence[Path] = (),
    root: Path = Path("."),
    output_excerpt_limit: int = DEFAULT_OUTPUT_EXCERPT_LIMIT,
) -> DeploymentCommandTranscript:
    """Build deterministic local transcript evidence from explicit command-result metadata."""

    command_tuple = _command_tuple(command)
    purpose = purpose.strip()
    if not purpose:
        raise DeploymentCommandTranscriptError("purpose cannot be empty.")
    if not started_at.strip():
        raise DeploymentCommandTranscriptError("started_at cannot be empty.")
    if not finished_at.strip():
        raise DeploymentCommandTranscriptError("finished_at cannot be empty.")
    try:
        exit_code = int(exit_code)
    except (TypeError, ValueError) as exc:
        raise DeploymentCommandTranscriptError("exit_code must be an integer.") from exc
    if output_excerpt_limit <= 0:
        raise DeploymentCommandTranscriptError("output_excerpt_limit must be positive.")

    root = Path(root)
    artifacts = tuple(_artifact_summary(Path(path), root=root) for path in artifact_paths)
    return DeploymentCommandTranscript(
        purpose=purpose,
        command=command_tuple,
        exit_code=exit_code,
        started_at=started_at.strip(),
        finished_at=finished_at.strip(),
        stdout=_output_summary("stdout", stdout_text, output_excerpt_limit=output_excerpt_limit),
        stderr=_output_summary("stderr", stderr_text, output_excerpt_limit=output_excerpt_limit),
        artifacts=artifacts,
    )


def write_deployment_command_transcript(transcript: DeploymentCommandTranscript, output_path: Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(transcript.to_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def command_from_json(value: str) -> tuple[str, ...]:
    try:
        payload: Any = json.loads(value)
    except json.JSONDecodeError as exc:
        raise DeploymentCommandTranscriptError(f"command_json must be valid JSON: {exc}") from exc
    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
        raise DeploymentCommandTranscriptError("command_json must be a JSON array of strings.")
    return _command_tuple(payload)


def _command_tuple(command: Sequence[str]) -> tuple[str, ...]:
    if not isinstance(command, Sequence) or isinstance(command, (str, bytes)):
        raise DeploymentCommandTranscriptError("command must be a sequence of strings.")
    if any(not isinstance(part, str) for part in command):
        raise DeploymentCommandTranscriptError("command must contain only string parts.")
    values = tuple(command)
    if not values or any(not part.strip() for part in values):
        raise DeploymentCommandTranscriptError("command cannot be empty or contain blank parts.")
    return values


def _output_summary(stream: str, text: str, *, output_excerpt_limit: int) -> DeploymentCommandOutput:
    text = str(text)
    data = text.encode("utf-8")
    excerpt = text[:output_excerpt_limit]
    truncated = len(text) > output_excerpt_limit
    return DeploymentCommandOutput(
        stream=stream,
        sha256=hashlib.sha256(data).hexdigest(),
        length_bytes=len(data),
        excerpt=excerpt,
        truncated=truncated,
    )


def _artifact_summary(path: Path, *, root: Path) -> DeploymentCommandArtifact:
    absolute = root / path
    if not absolute.is_file():
        return DeploymentCommandArtifact(path=path, exists=False, size_bytes=None, sha256=None)
    return DeploymentCommandArtifact(
        path=path,
        exists=True,
        size_bytes=absolute.stat().st_size,
        sha256=_sha256(absolute),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
