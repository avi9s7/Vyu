from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


class JobRepositoryError(Exception):
    """Base job repository error."""


class InvalidJobTransition(JobRepositoryError):
    """Raised when a job state transition is not allowed."""


class IdempotencyConflict(JobRepositoryError):
    """Raised when an idempotency key is reused with a different request body."""


@dataclass(frozen=True)
class NewJob:
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    kind: str
    payload: dict[str, object]
    max_attempts: int = 3


@dataclass(frozen=True)
class JobRecord:
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    kind: str
    status: str
    attempt: int
    max_attempts: int
    payload: dict[str, object]
    result: dict[str, object] | None
    error_code: str | None
    available_at: datetime
    leased_until: datetime | None
    lease_owner: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


@dataclass(frozen=True)
class JobLease:
    job_id: UUID
    worker_id: str
    leased_until: datetime
    attempt: int


@dataclass(frozen=True)
class HandlerResult:
    outcome: str
    result: dict[str, object] | None = None
    error_code: str | None = None
    retryable: bool = False


@dataclass(frozen=True)
class IdempotencyRequest:
    tenant_id: UUID
    actor_id: str
    route: str
    key: str
    request_sha256: str
    expires_at: datetime


@dataclass(frozen=True)
class IdempotencyResult:
    created: bool
    resource_type: str
    resource_id: str
    response_status: int
