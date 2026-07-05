from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ArtifactRecord:
    phase: str
    path: str
    artifact_type: str
    source_ids: list[str] = field(default_factory=list)
    checksum_sha256: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "path": self.path,
            "artifact_type": self.artifact_type,
            "source_ids": list(self.source_ids),
            "checksum_sha256": self.checksum_sha256,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ArtifactRecord":
        return cls(
            phase=str(payload["phase"]),
            path=str(payload["path"]),
            artifact_type=str(payload["artifact_type"]),
            source_ids=list(payload.get("source_ids", [])),
            checksum_sha256=payload.get("checksum_sha256"),
        )


@dataclass(frozen=True)
class ArtifactManifest:
    run_id: str
    environment: str
    tenant_id: str
    workspace_id: str
    corpus_version: str
    index_version: str
    artifacts: list[ArtifactRecord]
    sources: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "environment": self.environment,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "corpus_version": self.corpus_version,
            "index_version": self.index_version,
            "artifacts": [artifact.to_json() for artifact in self.artifacts],
            "sources": [dict(source) for source in self.sources],
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ArtifactManifest":
        return cls(
            run_id=str(payload["run_id"]),
            environment=str(payload["environment"]),
            tenant_id=str(payload["tenant_id"]),
            workspace_id=str(payload["workspace_id"]),
            corpus_version=str(payload["corpus_version"]),
            index_version=str(payload["index_version"]),
            artifacts=[
                ArtifactRecord.from_json(artifact)
                for artifact in payload.get("artifacts", [])
            ],
            sources=[dict(source) for source in payload.get("sources", [])],
        )

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json(), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @classmethod
    def read(cls, path: Path) -> "ArtifactManifest":
        return cls.from_json(json.loads(path.read_text(encoding="utf-8")))
