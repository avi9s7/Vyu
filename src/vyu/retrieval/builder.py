from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from src.vyu.ingestion.chunking import CHUNKER_NAME, CHUNKER_VERSION
from src.vyu.ingestion.models import DocumentChunk
from src.vyu.ingestion.repository import IngestionRepository
from src.vyu.jobs.contracts import JobRecord
from src.vyu.jobs.models import Job
from src.vyu.jobs.repository import JobRepository
from src.vyu.retrieval.embeddings import DeterministicEmbeddingProvider, EmbeddingProvider
from src.vyu.retrieval.evaluation_runner import evaluate_index_for_activation
from src.vyu.retrieval.index_contracts import (
    EmbeddingDimensionMismatchError,
    IndexManifest,
    IndexStatus,
    manifest_checksum,
)
from src.vyu.retrieval.metrics import RetrievalMetricsRecorder
from src.vyu.retrieval.models import RetrievalIndex
from src.vyu.retrieval.repository import RetrievalIndexRepository
from src.vyu.retrieval.settings import RetrievalSettings


def _safe_index_suffix(index_id: UUID) -> str:
    return re.sub(r"[^a-z0-9_]", "_", str(index_id).replace("-", "_"))


@dataclass(frozen=True)
class IndexBuildResult:
    outcome: str
    result: dict[str, object] | None = None
    error_code: str | None = None
    retryable: bool = False


class IndexBuildExecutor:
    def __init__(
        self,
        *,
        settings: RetrievalSettings | None = None,
        index_repository: RetrievalIndexRepository | None = None,
        ingestion_repository: IngestionRepository | None = None,
        job_repository: JobRepository | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        metrics: RetrievalMetricsRecorder | None = None,
    ) -> None:
        self.settings = settings or RetrievalSettings()
        self.index_repository = index_repository or RetrievalIndexRepository()
        self.ingestion_repository = ingestion_repository or IngestionRepository()
        self.job_repository = job_repository or JobRepository()
        self.embedding_provider = embedding_provider or DeterministicEmbeddingProvider(
            provider=self.settings.embedding_provider,
            default_model=self.settings.embedding_model,
        )
        self.metrics = metrics or RetrievalMetricsRecorder()

    def execute(
        self,
        job: JobRecord,
        *,
        session: Session,
        heartbeat: Callable[[], None],
    ) -> IndexBuildResult:
        simulate = job.payload.get("simulate")
        if simulate == "retry":
            return IndexBuildResult(outcome="retry", error_code="transient", retryable=True)
        if simulate == "fail":
            return IndexBuildResult(outcome="terminal_failure", error_code="build_failed")

        index_id = UUID(str(job.payload["retrieval_index_id"]))
        row = session.scalar(select(RetrievalIndex).where(RetrievalIndex.id == index_id))
        if not isinstance(row, RetrievalIndex):
            return IndexBuildResult(
                outcome="terminal_failure",
                error_code="retrieval_index_not_found",
            )

        if row.status == IndexStatus.ACTIVE.value:
            return IndexBuildResult(
                outcome="complete",
                result=self._completed_payload(row),
            )
        if row.status in {IndexStatus.FAILED.value, IndexStatus.RETIRED.value}:
            return IndexBuildResult(
                outcome="complete",
                result={"status": row.status, "retrieval_index_id": str(row.id)},
            )

        if self._is_cancelled(session, job):
            self.index_repository.update_status(session, index_id=index_id, status=IndexStatus.FAILED)
            return IndexBuildResult(
                outcome="complete",
                result={"status": "cancelled", "retrieval_index_id": str(index_id)},
            )

        manifest = IndexManifest.from_json(dict(row.manifest_json))
        try:
            manifest.validate_dimensions()
        except EmbeddingDimensionMismatchError as exc:
            self.index_repository.update_status(session, index_id=index_id, status=IndexStatus.FAILED)
            return IndexBuildResult(
                outcome="terminal_failure",
                error_code="embedding_dimension_mismatch",
                result={"message": str(exc)},
            )

        self.metrics.record_index_build_started(use_case=manifest.use_case)
        started = time.perf_counter()
        try:
            chunk_count = self._embed_snapshot(
                session,
                row=row,
                manifest=manifest,
                heartbeat=heartbeat,
            )
            self._build_database_indexes(session, index_id=index_id)
            session.execute(text("ANALYZE chunk_embeddings"))
            evaluation = evaluate_index_for_activation(
                suite=self.settings.evaluation_suite,
                chunk_count=chunk_count,
                document_count=row.document_count,
            )
            self.index_repository.update_status(
                session,
                index_id=index_id,
                status=IndexStatus.VALIDATING,
                evaluation_result=evaluation,
            )
            if evaluation.passed:
                activated = self.index_repository.activate_index(
                    session,
                    index_id=index_id,
                    tenant_id=row.tenant_id,
                    workspace_id=row.workspace_id,
                    use_case=row.use_case,
                )
                self.metrics.record_index_activation(use_case=activated.use_case)
            else:
                self.index_repository.update_status(
                    session,
                    index_id=index_id,
                    status=IndexStatus.FAILED,
                )
                self.metrics.record_index_failure(use_case=manifest.use_case)
                return IndexBuildResult(
                    outcome="terminal_failure",
                    error_code="evaluation_failed",
                    result={"evaluation": evaluation.to_json()},
                )
        except Exception as exc:
            self.index_repository.update_status(session, index_id=index_id, status=IndexStatus.FAILED)
            self.metrics.record_index_failure(use_case=manifest.use_case)
            return IndexBuildResult(
                outcome="retry" if self._is_retryable(exc) else "terminal_failure",
                error_code="index_build_failed",
                result={"message": str(exc)},
                retryable=self._is_retryable(exc),
            )

        elapsed_ms = RetrievalMetricsRecorder.elapsed_ms(started)
        return IndexBuildResult(
            outcome="complete",
            result={
                "status": IndexStatus.ACTIVE.value,
                "retrieval_index_id": str(index_id),
                "manifest_checksum": manifest_checksum(manifest),
                "chunk_count": chunk_count,
                "latency_ms": int(elapsed_ms),
            },
        )

    def _embed_snapshot(
        self,
        session: Session,
        *,
        row: RetrievalIndex,
        manifest: IndexManifest,
        heartbeat: Callable[[], None],
    ) -> int:
        chunks: list[DocumentChunk] = []
        for ref in manifest.document_versions:
            version_id = UUID(ref.document_version_id)
            version = self.ingestion_repository.get_version(session, version_id)
            if version is None:
                raise RuntimeError(f"snapshot version missing: {ref.document_version_id}")
            chunks.extend(self.ingestion_repository.list_chunks(session, version_id))

        if not chunks:
            return 0

        batch_size = max(1, self.settings.embed_batch_size)
        embedded = 0
        for offset in range(0, len(chunks), batch_size):
            heartbeat()
            batch_chunks = chunks[offset : offset + batch_size]
            text_hashes = tuple(chunk.text_sha256 for chunk in batch_chunks)
            cached = self.index_repository.lookup_cached_embeddings(
                session,
                tenant_id=row.tenant_id,
                text_hashes=text_hashes,
                provider=self.settings.embedding_provider,
                model=self.settings.embedding_model,
                dimensions=manifest.embedding_dimensions,
            )
            missing = [chunk for chunk in batch_chunks if chunk.text_sha256 not in cached]
            if missing:
                batch = self._embed_with_retry([chunk.text for chunk in missing], manifest)
                for chunk_index, chunk in enumerate(missing):
                    self.index_repository.save_embedding_batch(
                        session,
                        tenant_id=row.tenant_id,
                        workspace_id=row.workspace_id,
                        retrieval_index_id=row.id,
                        document_chunk_id=chunk.id,
                        batch=batch,
                        vector_index=chunk_index,
                        chunk_text=chunk.text,
                    )
            for chunk in batch_chunks:
                if chunk in missing:
                    continue
                self.index_repository.link_cached_embedding(
                    session,
                    tenant_id=row.tenant_id,
                    workspace_id=row.workspace_id,
                    retrieval_index_id=row.id,
                    document_chunk_id=chunk.id,
                    cached=cached[chunk.text_sha256],
                    chunk_text=chunk.text,
                )
            embedded += len(batch_chunks)
        row.chunk_count = embedded
        row.chunker_name = CHUNKER_NAME
        row.chunker_version = CHUNKER_VERSION
        session.flush()
        return embedded

    def _embed_with_retry(self, texts: list[str], manifest: IndexManifest):
        last_error: Exception | None = None
        for _attempt in range(self.settings.embed_max_attempts):
            try:
                batch = self.embedding_provider.embed(
                    texts,
                    model=manifest.embedding_model,
                    dimensions=manifest.embedding_dimensions,
                )
                self.metrics.record_embedding_batch(
                    provider=batch.provider,
                    batch_size=len(texts),
                    latency_ms=float(batch.latency_ms),
                )
                return batch
            except Exception as exc:
                last_error = exc
                if not self._is_retryable(exc):
                    raise
        if last_error is not None:
            raise last_error
        raise RuntimeError("embedding failed without error")

    def _build_database_indexes(self, session: Session, *, index_id: UUID) -> None:
        suffix = _safe_index_suffix(index_id)
        session.execute(
            text(
                f"""
                CREATE INDEX IF NOT EXISTS ix_chunk_embeddings_hnsw_{suffix}
                ON chunk_embeddings
                USING hnsw (embedding vector_cosine_ops)
                WHERE retrieval_index_id = :index_id
                """
            ),
            {"index_id": index_id},
        )
        session.execute(
            text(
                f"""
                CREATE INDEX IF NOT EXISTS ix_chunk_embeddings_gin_{suffix}
                ON chunk_embeddings
                USING gin (search_vector)
                WHERE retrieval_index_id = :index_id
                """
            ),
            {"index_id": index_id},
        )
        row = session.scalar(select(RetrievalIndex).where(RetrievalIndex.id == index_id))
        if isinstance(row, RetrievalIndex):
            row.lexical_config_json = {
                "index_name": f"ix_chunk_embeddings_gin_{suffix}",
                "ts_config": "english",
            }
            row.semantic_config_json = {
                "index_name": f"ix_chunk_embeddings_hnsw_{suffix}",
                "distance": "cosine",
            }
            session.flush()

    def _is_cancelled(self, session: Session, job: JobRecord) -> bool:
        row = session.scalar(select(Job).where(Job.id == job.id))
        return isinstance(row, Job) and row.status == "cancelled"

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        message = str(exc).lower()
        return "timeout" in message or "429" in message or "transient" in message

    @staticmethod
    def _completed_payload(row: RetrievalIndex) -> dict[str, object]:
        return {
            "status": row.status,
            "retrieval_index_id": str(row.id),
            "manifest_checksum": row.manifest_checksum,
            "chunk_count": row.chunk_count,
        }
