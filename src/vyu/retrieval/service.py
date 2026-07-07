from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.vyu.api.schemas.retrieval import (
    INDEX_BUILD_ROUTE,
    CreateIndexBuildRequest,
    IndexBuildCreatedResponse,
    IndexRecordListResponse,
    IndexRecordSummary,
    ResearchEvidenceExclusionSummary,
    ResearchEvidenceItem,
    ResearchEvidenceListResponse,
)
from src.vyu.auth.principal import RequestPrincipal
from src.vyu.db.repositories.audit import AuditRepository, NewAuditEvent
from src.vyu.ingestion.chunking import CHUNKER_NAME, CHUNKER_VERSION
from src.vyu.jobs.contracts import IdempotencyRequest, NewJob
from src.vyu.jobs.models import Job, OutboxEvent
from src.vyu.jobs.repository import IdempotencyConflict, JobRepository
from src.vyu.jobs.models import ResearchRun
from src.vyu.retrieval.index_contracts import (
    APPROVED_EMBEDDING_DIMENSIONS,
    DEFAULT_RETRIEVAL_USE_CASE,
    IndexManifest,
    IndexStatus,
)
from src.vyu.retrieval.models import RetrievalExclusion, RetrievalHitRow, RetrievalIndex, RetrievalRun
from src.vyu.retrieval.postgres import PostgresHybridRetrievalService
from src.vyu.retrieval.repository import RetrievalIndexRepository
from src.vyu.retrieval.settings import RetrievalSettings
from src.vyu.retrieval.snapshot import snapshot_ready_documents


class RetrievalServiceError(Exception):
    def __init__(self, *, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class RetrievalNotFound(RetrievalServiceError):
    def __init__(self) -> None:
        super().__init__(
            code="not_found",
            message="The requested resource was not found.",
            status_code=404,
        )


class RetrievalIdempotencyConflict(RetrievalServiceError):
    def __init__(self) -> None:
        super().__init__(
            code="idempotency_conflict",
            message="Idempotency key was reused with a different request body.",
            status_code=409,
        )


@dataclass(frozen=True)
class RetrievalService:
    settings: RetrievalSettings
    index_repository: RetrievalIndexRepository = RetrievalIndexRepository()
    hybrid_service: PostgresHybridRetrievalService | None = None
    job_repository: JobRepository = JobRepository()

    @classmethod
    def from_settings(cls, settings: RetrievalSettings) -> "RetrievalService":
        return cls(
            settings=settings,
            hybrid_service=PostgresHybridRetrievalService(settings=settings),
        )

    def create_index_build(
        self,
        *,
        body: CreateIndexBuildRequest,
        principal: RequestPrincipal,
        idempotency_key: str,
        request_id: str,
        trace_id: str,
        session: Session,
    ) -> IndexBuildCreatedResponse:
        request_sha256 = hashlib.sha256(
            json.dumps(body.model_dump(mode="json"), sort_keys=True).encode("utf-8")
        ).hexdigest()
        idempotency_request = IdempotencyRequest(
            tenant_id=principal.tenant_id,
            actor_id=principal.subject,
            route=INDEX_BUILD_ROUTE,
            key=idempotency_key,
            request_sha256=request_sha256,
            expires_at=datetime.now(tz=UTC) + timedelta(hours=self.settings.idempotency_ttl_hours),
        )

        def create_resource() -> tuple[str, str, int]:
            snapshot = snapshot_ready_documents(
                session,
                tenant_id=principal.tenant_id,
                workspace_id=principal.workspace_id,
                source_ids=tuple(body.source_ids) if body.source_ids else None,
            )
            manifest = IndexManifest(
                tenant_id=principal.tenant_id,
                workspace_id=principal.workspace_id,
                use_case=body.use_case or DEFAULT_RETRIEVAL_USE_CASE,
                source_ids=snapshot.source_ids,
                document_versions=snapshot.document_versions,
                chunker_name=CHUNKER_NAME,
                chunker_version=CHUNKER_VERSION,
                embedding_provider=self.settings.embedding_provider,
                embedding_model=self.settings.embedding_model,
                embedding_dimensions=APPROVED_EMBEDDING_DIMENSIONS,
                build_git_sha=self.settings.git_sha,
                policy_version=body.policy_version,
            )
            index = self.index_repository.create_index(
                session,
                manifest=manifest,
                document_count=snapshot.document_count,
                chunk_count=0,
                status=IndexStatus.BUILDING,
            )
            job_id = uuid4()
            outbox_id = uuid4()
            audit_id = uuid4()
            now = datetime.now(tz=UTC)
            self.job_repository.create_job(
                NewJob(
                    id=job_id,
                    tenant_id=principal.tenant_id,
                    workspace_id=principal.workspace_id,
                    kind="retrieval.index_build",
                    payload={"retrieval_index_id": str(index.index_id)},
                ),
                session,
            )
            session.add(
                OutboxEvent(
                    id=outbox_id,
                    tenant_id=principal.tenant_id,
                    workspace_id=principal.workspace_id,
                    topic="jobs",
                    aggregate_type="job",
                    aggregate_id=str(job_id),
                    payload={
                        "schema_version": 1,
                        "message_id": str(outbox_id),
                        "job_id": str(job_id),
                        "tenant_id": str(principal.tenant_id),
                        "workspace_id": str(principal.workspace_id),
                        "kind": "retrieval.index_build",
                        "attempt": 0,
                        "created_at": now.isoformat(),
                    },
                )
            )
            AuditRepository(session).append(
                NewAuditEvent(
                    id=audit_id,
                    tenant_id=principal.tenant_id,
                    workspace_id=principal.workspace_id,
                    actor_type="user",
                    actor_id=principal.subject,
                    request_id=request_id,
                    trace_id=trace_id,
                    event_type="retrieval_index_build_requested",
                    resource_type="retrieval_index",
                    resource_id=str(index.index_id),
                    outcome="success",
                    payload_sha256=request_sha256,
                    details={"job_id": str(job_id), "reason": body.reason},
                )
            )
            session.flush()
            return ("retrieval_index", str(index.index_id), 202)

        try:
            result = self.job_repository.get_or_create_idempotent(
                idempotency_request,
                create_resource,
                session,
            )
        except IdempotencyConflict as exc:
            raise RetrievalIdempotencyConflict() from exc

        index_id = UUID(result.resource_id)
        job_id = self._job_id_for_index(session, index_id)
        return IndexBuildCreatedResponse(
            retrieval_index_id=index_id,
            job_id=job_id,
            status="queued",
            links={"job": f"/v1/ingestion/jobs/{job_id}"},
        )

    def list_indexes(
        self,
        *,
        session: Session,
        status: str | None = None,
        limit: int = 20,
    ) -> IndexRecordListResponse:
        statement = select(RetrievalIndex).order_by(RetrievalIndex.created_at.desc()).limit(limit)
        if status is not None:
            statement = statement.where(RetrievalIndex.status == status)
        rows = session.scalars(statement).all()
        return IndexRecordListResponse(
            items=[
                IndexRecordSummary(
                    retrieval_index_id=row.id,
                    status=row.status,
                    use_case=row.use_case,
                    manifest_checksum=row.manifest_checksum,
                    document_count=row.document_count,
                    chunk_count=row.chunk_count,
                    created_at=row.created_at.isoformat(),
                )
                for row in rows
                if isinstance(row, RetrievalIndex)
            ]
        )

    def get_research_evidence(
        self,
        *,
        search_id: UUID,
        session: Session,
        cursor: str | None,
        limit: int,
    ) -> ResearchEvidenceListResponse:
        del cursor
        run = session.scalar(select(ResearchRun).where(ResearchRun.id == search_id))
        if not isinstance(run, ResearchRun):
            raise RetrievalNotFound()
        retrieval_run = session.scalar(
            select(RetrievalRun).where(RetrievalRun.workflow_run_id == str(search_id))
        )
        if not isinstance(retrieval_run, RetrievalRun):
            return ResearchEvidenceListResponse(
                items=[],
                exclusions=ResearchEvidenceExclusionSummary(total=0, kinds={}),
                abstention_reason="retrieval_not_completed",
            )
        hits = session.scalars(
            select(RetrievalHitRow)
            .where(RetrievalHitRow.retrieval_run_id == retrieval_run.id)
            .order_by(RetrievalHitRow.rank.asc())
            .limit(limit)
        ).all()
        exclusions = session.scalars(
            select(RetrievalExclusion).where(
                RetrievalExclusion.retrieval_run_id == retrieval_run.id
            )
        ).all()
        kinds: dict[str, int] = {}
        for exclusion in exclusions:
            if isinstance(exclusion, RetrievalExclusion):
                kinds[exclusion.exclusion_kind] = kinds.get(exclusion.exclusion_kind, 0) + 1
        return ResearchEvidenceListResponse(
            items=[
                ResearchEvidenceItem(
                    citation_id=hit.passage_id,
                    document_id=hit.document_id,
                    rank=hit.rank,
                    score_source=hit.score_source,
                    score_value=hit.score_value,
                    retrieval_index_id=retrieval_run.retrieval_index_id,
                    retrieval_run_id=retrieval_run.id,
                )
                for hit in hits
                if isinstance(hit, RetrievalHitRow)
            ],
            exclusions=ResearchEvidenceExclusionSummary(total=len(exclusions), kinds=kinds),
            abstention_reason=None if hits else "no_matching_evidence",
        )

    def _job_id_for_index(self, session: Session, index_id: UUID) -> UUID:
        row = session.scalar(
            select(Job)
            .where(Job.kind == "retrieval.index_build")
            .order_by(Job.created_at.desc())
        )
        if row is not None and str(row.payload.get("retrieval_index_id")) == str(index_id):
            return row.id
        rows = session.scalars(select(Job).where(Job.kind == "retrieval.index_build")).all()
        for candidate in rows:
            if str(candidate.payload.get("retrieval_index_id")) == str(index_id):
                return candidate.id
        return uuid4()
