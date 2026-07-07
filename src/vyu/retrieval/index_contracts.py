from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID

from src.vyu.research_mcp.hashing import stable_hash

APPROVED_EMBEDDING_DIMENSIONS = 1536
DEFAULT_RETRIEVAL_USE_CASE = "evidence_memory"


class IndexStatus(StrEnum):
    BUILDING = "building"
    VALIDATING = "validating"
    ACTIVE = "active"
    FAILED = "failed"
    RETIRED = "retired"


TERMINAL_INDEX_STATUSES = frozenset({IndexStatus.ACTIVE, IndexStatus.FAILED, IndexStatus.RETIRED})


@dataclass(frozen=True)
class DocumentVersionRef:
    document_id: str
    version_number: int
    document_version_id: str

    def to_json(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "version_number": self.version_number,
            "document_version_id": self.document_version_id,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "DocumentVersionRef":
        return cls(
            document_id=str(payload["document_id"]),
            version_number=int(payload["version_number"]),
            document_version_id=str(payload["document_version_id"]),
        )


@dataclass(frozen=True)
class IndexEvaluationResult:
    suite: str
    passed: bool
    metrics: dict[str, float] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "suite": self.suite,
            "passed": self.passed,
            "metrics": dict(self.metrics),
            "details": dict(self.details),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "IndexEvaluationResult":
        return cls(
            suite=str(payload["suite"]),
            passed=bool(payload["passed"]),
            metrics={
                str(key): float(value) for key, value in dict(payload.get("metrics", {})).items()
            },
            details=dict(payload.get("details", {})),
        )


@dataclass(frozen=True)
class IndexManifest:
    tenant_id: UUID
    workspace_id: UUID
    use_case: str
    source_ids: tuple[str, ...]
    document_versions: tuple[DocumentVersionRef, ...]
    chunker_name: str
    chunker_version: str
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    build_git_sha: str
    policy_version: str
    lexical_config: dict[str, Any] = field(default_factory=dict)
    semantic_config: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "tenant_id": str(self.tenant_id),
            "workspace_id": str(self.workspace_id),
            "use_case": self.use_case,
            "source_ids": list(self.source_ids),
            "document_versions": [item.to_json() for item in self.document_versions],
            "chunker_name": self.chunker_name,
            "chunker_version": self.chunker_version,
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "embedding_dimensions": self.embedding_dimensions,
            "build_git_sha": self.build_git_sha,
            "policy_version": self.policy_version,
            "lexical_config": dict(self.lexical_config),
            "semantic_config": dict(self.semantic_config),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "IndexManifest":
        return cls(
            tenant_id=UUID(str(payload["tenant_id"])),
            workspace_id=UUID(str(payload["workspace_id"])),
            use_case=str(payload.get("use_case", DEFAULT_RETRIEVAL_USE_CASE)),
            source_ids=tuple(str(item) for item in payload.get("source_ids", [])),
            document_versions=tuple(
                DocumentVersionRef.from_json(dict(item))
                for item in payload.get("document_versions", [])
            ),
            chunker_name=str(payload["chunker_name"]),
            chunker_version=str(payload["chunker_version"]),
            embedding_provider=str(payload["embedding_provider"]),
            embedding_model=str(payload["embedding_model"]),
            embedding_dimensions=int(payload["embedding_dimensions"]),
            build_git_sha=str(payload["build_git_sha"]),
            policy_version=str(payload["policy_version"]),
            lexical_config=dict(payload.get("lexical_config", {})),
            semantic_config=dict(payload.get("semantic_config", {})),
        )

    def validate_dimensions(self) -> None:
        if self.embedding_dimensions != APPROVED_EMBEDDING_DIMENSIONS:
            raise EmbeddingDimensionMismatchError(
                f"embedding dimensions {self.embedding_dimensions} do not match approved "
                f"dimension {APPROVED_EMBEDDING_DIMENSIONS}"
            )


def manifest_checksum(manifest: IndexManifest) -> str:
    return stable_hash(manifest.to_json())


@dataclass(frozen=True)
class IndexRecord:
    index_id: UUID
    tenant_id: UUID
    workspace_id: UUID
    use_case: str
    status: IndexStatus
    manifest: IndexManifest
    manifest_checksum: str
    document_count: int
    chunk_count: int
    evaluation_result: IndexEvaluationResult | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    activated_at: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "index_id": str(self.index_id),
            "tenant_id": str(self.tenant_id),
            "workspace_id": str(self.workspace_id),
            "use_case": self.use_case,
            "status": self.status.value,
            "manifest": self.manifest.to_json(),
            "manifest_checksum": self.manifest_checksum,
            "document_count": self.document_count,
            "chunk_count": self.chunk_count,
            "evaluation_result": (
                self.evaluation_result.to_json() if self.evaluation_result is not None else None
            ),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "activated_at": self.activated_at,
        }


class EmbeddingDimensionMismatchError(ValueError):
    """Raised when an embedding or manifest uses non-approved dimensions."""


class IndexActivationError(RuntimeError):
    """Raised when an index cannot be activated safely."""
