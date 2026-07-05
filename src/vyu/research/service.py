from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from src.vyu.api.schemas.research import (
    RESEARCH_ROUTE,
    CreateResearchSearchRequest,
    ResearchCancelResponse,
    ResearchEventItem,
    ResearchEventListResponse,
    ResearchSearchCreatedResponse,
    ResearchSearchDetail,
    ResearchSearchLinks,
    ResearchSearchListResponse,
    ResearchSearchSummary,
)
from src.vyu.auth.principal import RequestPrincipal
from src.vyu.db.repositories.audit import AuditRepository, NewAuditEvent
from src.vyu.jobs.contracts import IdempotencyConflict, IdempotencyRequest, NewJob
from src.vyu.jobs.models import Job, OutboxEvent, ResearchRun, ResearchRunEvent
from src.vyu.jobs.repository import JobRepository
from src.vyu.research.settings import ResearchSettings
from src.vyu.sources import SourceRegistry


class ResearchServiceError(Exception):
    def __init__(self, *, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class ResearchNotFound(ResearchServiceError):
    def __init__(self) -> None:
        super().__init__(
            code="not_found",
            message="The requested resource was not found.",
            status_code=404,
        )


class ResearchIdempotencyConflict(ResearchServiceError):
    def __init__(self) -> None:
        super().__init__(
            code="idempotency_conflict",
            message="Idempotency key was reused with a different request body.",
            status_code=409,
        )


@dataclass(frozen=True)
class ResearchService:
    settings: ResearchSettings
    source_registry: SourceRegistry
    job_repository: JobRepository = JobRepository()

    @classmethod
    def from_settings(cls, settings: ResearchSettings) -> ResearchService:
        registry = SourceRegistry.read(settings.source_registry_path)
        return cls(settings=settings, source_registry=registry)

    def create_search(
        self,
        *,
        body: CreateResearchSearchRequest,
        principal: RequestPrincipal,
        idempotency_key: str,
        request_id: str,
        trace_id: str,
        session: Session,
    ) -> ResearchSearchCreatedResponse:
        self._validate_submission(body, principal)
        request_sha256 = normalized_request_sha256(body)
        expires_at = datetime.now(tz=UTC) + timedelta(hours=self.settings.idempotency_ttl_hours)
        idempotency_request = IdempotencyRequest(
            tenant_id=principal.tenant_id,
            actor_id=principal.subject,
            route=RESEARCH_ROUTE,
            key=idempotency_key,
            request_sha256=request_sha256,
            expires_at=expires_at,
        )

        def create_resource() -> tuple[str, str, int]:
            search_id = uuid4()
            job_id = uuid4()
            outbox_id = uuid4()
            audit_id = uuid4()
            event_id = uuid4()
            now = datetime.now(tz=UTC)
            job_payload = self._job_payload(search_id=search_id, body=body)
            session.add(
                ResearchRun(
                    id=search_id,
                    tenant_id=principal.tenant_id,
                    workspace_id=principal.workspace_id,
                    created_by=principal.user_id,
                    question=body.question,
                    intended_use=body.intended_use,
                    requested_sources=list(body.source_ids),
                    status="queued",
                    cancel_requested=False,
                    policy_version=self.settings.policy_version,
                )
            )
            self.job_repository.create_job(
                NewJob(
                    id=job_id,
                    tenant_id=principal.tenant_id,
                    workspace_id=principal.workspace_id,
                    kind="research.run",
                    payload=job_payload,
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
                        "kind": "research.run",
                        "attempt": 0,
                        "created_at": now.isoformat(),
                    },
                )
            )
            session.add(
                ResearchRunEvent(
                    id=event_id,
                    tenant_id=principal.tenant_id,
                    workspace_id=principal.workspace_id,
                    research_run_id=search_id,
                    sequence=1,
                    event_type="research_search_created",
                    safe_message="Research search queued.",
                    details={"job_id": str(job_id), "status": "queued"},
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
                    event_type="research_search_submitted",
                    resource_type="research_run",
                    resource_id=str(search_id),
                    outcome="success",
                    payload_sha256=request_sha256,
                    details={"job_id": str(job_id), "source_ids": list(body.source_ids)},
                )
            )
            session.flush()
            return ("research_run", str(search_id), 202)

        try:
            result = self.job_repository.get_or_create_idempotent(
                idempotency_request,
                create_resource,
                session,
            )
        except IdempotencyConflict as exc:
            raise ResearchIdempotencyConflict() from exc

        search_id = UUID(result.resource_id)
        job_id = self._job_id_for_search(session, search_id)
        return self._created_response(search_id, job_id)

    def get_search(
        self,
        *,
        search_id: UUID,
        session: Session,
    ) -> ResearchSearchDetail:
        row = self._get_search_row(session, search_id)
        if row is None:
            raise ResearchNotFound()
        job_id = self._job_id_for_search(session, search_id)
        return ResearchSearchDetail(
            search_id=str(row.id),
            status=row.status,
            question=row.question,
            cancel_requested=row.cancel_requested,
            created_at=row.created_at.isoformat(),
            job_id=str(job_id) if job_id is not None else None,
            intended_use=row.intended_use,
            requested_sources=list(row.requested_sources),
            current_step=row.current_step,
            policy_version=row.policy_version,
            started_at=row.started_at.isoformat() if row.started_at else None,
            completed_at=row.completed_at.isoformat() if row.completed_at else None,
            links=self._links(row.id, job_id),
        )

    def list_searches(
        self,
        *,
        cursor: str | None,
        limit: int,
        session: Session,
    ) -> ResearchSearchListResponse:
        page_size = min(max(limit, 1), self.settings.max_page_size)
        statement = select(ResearchRun).order_by(
            ResearchRun.created_at.desc(),
            ResearchRun.id.desc(),
        )
        if cursor is not None:
            cursor_created_at, cursor_id = decode_cursor(cursor)
            statement = statement.where(
                or_(
                    ResearchRun.created_at < cursor_created_at,
                    and_(
                        ResearchRun.created_at == cursor_created_at,
                        ResearchRun.id < cursor_id,
                    ),
                )
            )
        rows = session.scalars(statement.limit(page_size + 1)).all()
        has_more = len(rows) > page_size
        page_rows = rows[:page_size]
        items: list[ResearchSearchSummary] = []
        for row in page_rows:
            job_id = self._job_id_for_search(session, row.id)
            items.append(
                ResearchSearchSummary(
                    search_id=str(row.id),
                    status=row.status,
                    question=row.question,
                    cancel_requested=row.cancel_requested,
                    created_at=row.created_at.isoformat(),
                    job_id=str(job_id) if job_id is not None else None,
                )
            )
        next_cursor = None
        if has_more and page_rows:
            last = page_rows[-1]
            next_cursor = encode_cursor(last.created_at, last.id)
        return ResearchSearchListResponse(items=items, next_cursor=next_cursor)

    def list_events(
        self,
        *,
        search_id: UUID,
        cursor: str | None,
        limit: int,
        session: Session,
    ) -> ResearchEventListResponse:
        if self._get_search_row(session, search_id) is None:
            raise ResearchNotFound()
        page_size = min(max(limit, 1), self.settings.max_page_size)
        statement = (
            select(ResearchRunEvent)
            .where(ResearchRunEvent.research_run_id == search_id)
            .order_by(ResearchRunEvent.sequence.asc())
        )
        if cursor is not None:
            cursor_sequence = int(cursor)
            statement = statement.where(ResearchRunEvent.sequence > cursor_sequence)
        rows = session.scalars(statement.limit(page_size + 1)).all()
        has_more = len(rows) > page_size
        page_rows = rows[:page_size]
        items = [
            ResearchEventItem(
                sequence=row.sequence,
                event_type=row.event_type,
                safe_message=row.safe_message,
                created_at=row.created_at.isoformat(),
                details=dict(row.details),
            )
            for row in page_rows
        ]
        next_cursor = str(page_rows[-1].sequence) if has_more and page_rows else None
        return ResearchEventListResponse(items=items, next_cursor=next_cursor)

    def cancel_search(
        self,
        *,
        search_id: UUID,
        principal: RequestPrincipal,
        request_id: str,
        trace_id: str,
        session: Session,
    ) -> ResearchCancelResponse:
        row = self._get_search_row(session, search_id)
        if row is None:
            raise ResearchNotFound()
        if not row.cancel_requested:
            row.cancel_requested = True
            job_id = self._job_id_for_search(session, search_id)
            if job_id is not None:
                self.job_repository.request_cancellation(job_id, session)
            next_sequence = self._next_event_sequence(session, search_id)
            session.add(
                ResearchRunEvent(
                    id=uuid4(),
                    tenant_id=row.tenant_id,
                    workspace_id=row.workspace_id,
                    research_run_id=search_id,
                    sequence=next_sequence,
                    event_type="research_search_cancel_requested",
                    safe_message="Cancellation requested.",
                    details={"requested_by": principal.subject},
                )
            )
            AuditRepository(session).append(
                NewAuditEvent(
                    id=uuid4(),
                    tenant_id=principal.tenant_id,
                    workspace_id=principal.workspace_id,
                    actor_type="user",
                    actor_id=principal.subject,
                    request_id=request_id,
                    trace_id=trace_id,
                    event_type="research_search_cancel_requested",
                    resource_type="research_run",
                    resource_id=str(search_id),
                    outcome="success",
                    payload_sha256="0" * 64,
                )
            )
            session.flush()
        return ResearchCancelResponse(
            search_id=str(search_id),
            status=row.status,
            cancel_requested=row.cancel_requested,
        )

    def _validate_submission(
        self,
        body: CreateResearchSearchRequest,
        principal: RequestPrincipal,
    ) -> None:
        if self.settings.requires_only_approved_sources and not body.only_approved_sources:
            raise ResearchServiceError(
                code="validation_error",
                message="only_approved_sources must be true in staging and production.",
                status_code=422,
            )
        for source_id in body.source_ids:
            try:
                if body.only_approved_sources:
                    self.source_registry.require_approved(
                        source_id,
                        intended_use=body.intended_use,
                        tenant_id=str(principal.tenant_id),
                        workspace_id=str(principal.workspace_id),
                    )
                else:
                    self.source_registry.get(source_id)
            except KeyError as exc:
                raise ResearchServiceError(
                    code="validation_error",
                    message=f"Unknown source ID: {source_id}",
                    status_code=422,
                ) from exc
            except PermissionError as exc:
                raise ResearchServiceError(
                    code="validation_error",
                    message=str(exc),
                    status_code=422,
                ) from exc

    def _get_search_row(self, session: Session, search_id: UUID) -> ResearchRun | None:
        return session.scalar(select(ResearchRun).where(ResearchRun.id == search_id))

    def _job_id_for_search(self, session: Session, search_id: UUID) -> UUID | None:
        job = session.scalar(
            select(Job).where(
                Job.kind == "research.run",
                Job.payload.contains({"research_run_id": str(search_id)}),
            )
        )
        return job.id if job is not None else None

    def _next_event_sequence(self, session: Session, search_id: UUID) -> int:
        latest = session.scalar(
            select(ResearchRunEvent.sequence)
            .where(ResearchRunEvent.research_run_id == search_id)
            .order_by(ResearchRunEvent.sequence.desc())
            .limit(1)
        )
        return 1 if latest is None else int(latest) + 1

    def _created_response(
        self,
        search_id: UUID,
        job_id: UUID | None,
    ) -> ResearchSearchCreatedResponse:
        return ResearchSearchCreatedResponse(
            search_id=str(search_id),
            job_id=str(job_id) if job_id is not None else "",
            status="queued",
            links=self._links(search_id, job_id),
        )

    def _links(self, search_id: UUID, job_id: UUID | None) -> ResearchSearchLinks:
        base = f"/v1/research/searches/{search_id}"
        return ResearchSearchLinks(
            self=base,
            events=f"{base}/events",
            job=f"/v1/jobs/{job_id}" if job_id is not None else "",
        )

    def _job_payload(
        self,
        *,
        search_id: UUID,
        body: CreateResearchSearchRequest,
    ) -> dict[str, object]:
        return {
            "research_run_id": str(search_id),
            "question": body.question,
            "source_ids": list(body.source_ids),
            "intended_use": body.intended_use,
            "date_from": body.date_from.isoformat() if body.date_from else None,
            "date_to": body.date_to.isoformat() if body.date_to else None,
            "evidence_types": [value.value for value in body.evidence_types],
            "population": body.population,
            "intervention": body.intervention,
            "comparator": body.comparator,
            "only_approved_sources": body.only_approved_sources,
            "policy_version": self.settings.policy_version,
        }


def normalized_request_sha256(body: CreateResearchSearchRequest) -> str:
    payload = json.dumps(
        body.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def encode_cursor(created_at: datetime, search_id: UUID) -> str:
    return f"{created_at.isoformat()}|{search_id}"


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    created_at_raw, search_id_raw = cursor.split("|", 1)
    return datetime.fromisoformat(created_at_raw), UUID(search_id_raw)
