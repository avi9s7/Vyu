from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.vyu.db.models.audit import AuditEvent
from src.vyu.db.session import TenantScope


class AuditRepositoryError(Exception):
    """Base audit repository error."""


class DuplicateAuditEventError(AuditRepositoryError):
    """Raised when an audit event id already exists."""


@dataclass(frozen=True)
class AuditEventRecord:
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    actor_type: str
    actor_id: str
    request_id: str
    trace_id: str | None
    event_type: str
    resource_type: str
    resource_id: str
    outcome: str
    payload_sha256: str
    details: dict[str, object]
    occurred_at: datetime


@dataclass(frozen=True)
class NewAuditEvent:
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    actor_type: str
    actor_id: str
    request_id: str
    event_type: str
    resource_type: str
    resource_id: str
    outcome: str
    payload_sha256: str
    trace_id: str | None = None
    details: dict[str, object] | None = None


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, event: NewAuditEvent) -> AuditEventRecord:
        row = AuditEvent(
            id=event.id,
            tenant_id=event.tenant_id,
            workspace_id=event.workspace_id,
            actor_type=event.actor_type,
            actor_id=event.actor_id,
            request_id=event.request_id,
            trace_id=event.trace_id,
            event_type=event.event_type,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            outcome=event.outcome,
            payload_sha256=event.payload_sha256,
            details=event.details or {},
        )
        try:
            self._session.add(row)
            self._session.flush()
        except IntegrityError as exc:
            raise DuplicateAuditEventError("audit event already exists") from exc
        return AuditEventRecord(
            id=row.id,
            tenant_id=row.tenant_id,
            workspace_id=row.workspace_id,
            actor_type=row.actor_type,
            actor_id=row.actor_id,
            request_id=row.request_id,
            trace_id=row.trace_id,
            event_type=row.event_type,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            outcome=row.outcome,
            payload_sha256=row.payload_sha256,
            details=row.details,
            occurred_at=row.occurred_at,
        )

    def list_for_resource(
        self,
        *,
        scope: TenantScope,
        resource_type: str,
        resource_id: str,
        limit: int = 100,
    ) -> list[AuditEventRecord]:
        rows = self._session.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.tenant_id == scope.tenant_id,
                AuditEvent.workspace_id == scope.workspace_id,
                AuditEvent.resource_type == resource_type,
                AuditEvent.resource_id == resource_id,
            )
            .order_by(AuditEvent.occurred_at.desc())
            .limit(limit)
        ).all()
        return [
            AuditEventRecord(
                id=row.id,
                tenant_id=row.tenant_id,
                workspace_id=row.workspace_id,
                actor_type=row.actor_type,
                actor_id=row.actor_id,
                request_id=row.request_id,
                trace_id=row.trace_id,
                event_type=row.event_type,
                resource_type=row.resource_type,
                resource_id=row.resource_id,
                outcome=row.outcome,
                payload_sha256=row.payload_sha256,
                details=row.details,
                occurred_at=row.occurred_at,
            )
            for row in rows
        ]
