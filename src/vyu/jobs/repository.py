from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.vyu.jobs.contracts import (
    IdempotencyConflict,
    IdempotencyRequest,
    IdempotencyResult,
    InvalidJobTransition,
    JobLease,
    JobRecord,
    NewJob,
)
from src.vyu.jobs.models import IdempotencyKey, Job

TERMINAL_STATUSES = frozenset({"succeeded", "blocked", "cancelled"})
RUNNING_FROM = frozenset({"queued"})
RUNNING_TO = frozenset({"succeeded", "failed", "blocked", "cancelled"})
QUEUED_TO = frozenset({"running", "cancelled"})
FAILED_TO = frozenset({"queued"})


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _to_record(row: Job) -> JobRecord:
    return JobRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        workspace_id=row.workspace_id,
        kind=row.kind,
        status=row.status,
        attempt=row.attempt,
        max_attempts=row.max_attempts,
        payload=row.payload,
        result=row.result,
        error_code=row.error_code,
        available_at=row.available_at,
        leased_until=row.leased_until,
        lease_owner=row.lease_owner,
        created_at=row.created_at,
        updated_at=row.updated_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


def _assert_transition(current: str, target: str, *, row: Job | None = None) -> None:
    if current == "queued" and target in QUEUED_TO:
        return
    if current == "running" and target in RUNNING_TO:
        return
    if current == "failed" and target in FAILED_TO:
        if row is None or row.attempt >= row.max_attempts:
            raise InvalidJobTransition(f"cannot retry job in status {current}")
        if row.available_at is None:
            raise InvalidJobTransition("failed job retry requires available_at")
        return
    raise InvalidJobTransition(f"invalid transition {current} -> {target}")


class JobRepository:
    def create_job(self, new_job: NewJob, session: Session) -> JobRecord:
        row = Job(
            id=new_job.id,
            tenant_id=new_job.tenant_id,
            workspace_id=new_job.workspace_id,
            kind=new_job.kind,
            status="queued",
            attempt=0,
            max_attempts=new_job.max_attempts,
            payload=new_job.payload,
            available_at=_utcnow(),
        )
        session.add(row)
        session.flush()
        return _to_record(row)

    def acquire_job(
        self,
        job_id: UUID,
        worker_id: str,
        lease_seconds: int,
        session: Session,
    ) -> JobLease | None:
        now = _utcnow()
        row = session.scalar(
            select(Job)
            .where(
                Job.id == job_id,
                Job.status == "queued",
                Job.available_at <= now,
            )
            .with_for_update(skip_locked=True)
        )
        if row is None:
            return None
        if row.leased_until is not None and row.leased_until > now:
            return None
        _assert_transition(row.status, "running")
        leased_until = now + timedelta(seconds=lease_seconds)
        row.status = "running"
        row.attempt = row.attempt + 1
        row.lease_owner = worker_id
        row.leased_until = leased_until
        row.started_at = row.started_at or now
        session.flush()
        return JobLease(
            job_id=row.id,
            worker_id=worker_id,
            leased_until=leased_until,
            attempt=row.attempt,
        )

    def extend_lease(
        self,
        job_id: UUID,
        worker_id: str,
        lease_seconds: int,
        session: Session,
    ) -> JobLease:
        row = session.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if row is None or row.lease_owner != worker_id or row.status != "running":
            raise InvalidJobTransition("cannot extend lease for job")
        leased_until = _utcnow() + timedelta(seconds=lease_seconds)
        row.leased_until = leased_until
        session.flush()
        return JobLease(
            job_id=row.id,
            worker_id=worker_id,
            leased_until=leased_until,
            attempt=row.attempt,
        )

    def complete_job(
        self,
        job_id: UUID,
        worker_id: str,
        result: dict[str, object],
        session: Session,
    ) -> JobRecord:
        row = session.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if row is None or row.lease_owner != worker_id:
            raise InvalidJobTransition("cannot complete job")
        _assert_transition(row.status, "succeeded")
        now = _utcnow()
        row.status = "succeeded"
        row.result = result
        row.completed_at = now
        row.leased_until = None
        row.lease_owner = None
        session.flush()
        return _to_record(row)

    def fail_job(
        self,
        job_id: UUID,
        worker_id: str,
        error_code: str,
        retry_at: datetime | None,
        session: Session,
    ) -> JobRecord:
        row = session.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if row is None or row.lease_owner != worker_id:
            raise InvalidJobTransition("cannot fail job")
        _assert_transition(row.status, "failed")
        now = _utcnow()
        row.error_code = error_code
        row.leased_until = None
        row.lease_owner = None
        if retry_at is not None and row.attempt < row.max_attempts:
            row.status = "queued"
            row.available_at = retry_at
        else:
            row.status = "failed"
            row.completed_at = now
        session.flush()
        return _to_record(row)

    def request_cancellation(self, job_id: UUID, session: Session) -> JobRecord:
        row = session.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if row is None:
            raise InvalidJobTransition("job not found")
        if row.status in TERMINAL_STATUSES:
            return _to_record(row)
        if row.status == "running":
            row.status = "cancelled"
        elif row.status == "queued":
            _assert_transition(row.status, "cancelled")
            row.status = "cancelled"
        else:
            raise InvalidJobTransition(f"cannot cancel job in status {row.status}")
        row.completed_at = _utcnow()
        row.leased_until = None
        row.lease_owner = None
        session.flush()
        return _to_record(row)

    def get_job(self, job_id: UUID, session: Session) -> JobRecord | None:
        row = session.scalar(select(Job).where(Job.id == job_id))
        if row is None:
            return None
        return _to_record(row)

    def get_or_create_idempotent(
        self,
        request: IdempotencyRequest,
        create_resource: Callable[[], tuple[str, str, int]],
        session: Session,
    ) -> IdempotencyResult:
        existing = session.scalar(
            select(IdempotencyKey).where(
                IdempotencyKey.tenant_id == request.tenant_id,
                IdempotencyKey.actor_id == request.actor_id,
                IdempotencyKey.route == request.route,
                IdempotencyKey.key == request.key,
            )
        )
        if existing is not None:
            if existing.request_sha256 != request.request_sha256:
                raise IdempotencyConflict("idempotency key reused with different request")
            return IdempotencyResult(
                created=False,
                resource_type=existing.resource_type,
                resource_id=existing.resource_id,
                response_status=existing.response_status,
            )
        resource_type, resource_id, response_status = create_resource()
        row = IdempotencyKey(
            tenant_id=request.tenant_id,
            actor_id=request.actor_id,
            route=request.route,
            key=request.key,
            request_sha256=request.request_sha256,
            resource_type=resource_type,
            resource_id=resource_id,
            response_status=response_status,
            expires_at=request.expires_at,
        )
        session.add(row)
        session.flush()
        return IdempotencyResult(
            created=True,
            resource_type=resource_type,
            resource_id=resource_id,
            response_status=response_status,
        )
