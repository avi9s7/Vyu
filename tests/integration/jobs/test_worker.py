from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.vyu.db.session import TenantScope, build_engine, build_session_factory, transaction
from src.vyu.db.settings import DatabaseSettings
from src.vyu.jobs.contracts import NewJob
from src.vyu.jobs.models import Job
from src.vyu.jobs.repository import JobRepository
from src.vyu.jobs.worker import (
    HandlerResult,
    JobWorker,
    MessageDisposition,
    ResearchRunStubHandler,
    WorkerRunner,
    WorkerSettings,
    received_message_from_job,
)


@dataclass
class CountingHandler:
    calls: int = 0

    def handle(self, job, *, session, heartbeat) -> HandlerResult:
        del session, heartbeat
        self.calls += 1
        return HandlerResult(outcome="complete", result={"calls": self.calls})


class StubSqsConsumer:
    def __init__(self, messages: list) -> None:
        self.messages = list(messages)
        self.deleted: list[str] = []

    def receive(self, *, max_messages: int = 1):
        del max_messages
        if not self.messages:
            return []
        return [self.messages.pop(0)]

    def delete(self, receipt_handle: str) -> None:
        self.deleted.append(receipt_handle)

    def extend_visibility(self, receipt_handle: str, timeout_seconds: int) -> None:
        del receipt_handle, timeout_seconds


def _factory(url: str):
    return build_session_factory(build_engine(DatabaseSettings(database_url=url)))


def _create_job(
    factory,
    scope: TenantScope,
    *,
    payload: dict[str, object] | None = None,
    max_attempts: int = 3,
    kind: str = "research.run",
) -> Job:
    job_id = uuid4()
    repo = JobRepository()
    with transaction(factory, scope=scope) as session:
        record = repo.create_job(
            NewJob(
                id=job_id,
                tenant_id=scope.tenant_id,
                workspace_id=scope.workspace_id,
                kind=kind,
                payload=payload or {"simulate": "complete"},
                max_attempts=max_attempts,
            ),
            session,
        )
    with transaction(factory, scope=scope) as session:
        row = session.scalar(select(Job).where(Job.id == record.id))
        assert row is not None
        return row


@pytest.fixture
def worker_scope(postgres_urls: dict[str, str]) -> tuple[str, TenantScope]:
    tenant_id = uuid4()
    workspace_id = uuid4()
    return postgres_urls["migration"], TenantScope(tenant_id=tenant_id, workspace_id=workspace_id)


def test_duplicate_delivery_for_terminal_job_acks_without_handler(
    worker_scope: tuple[str, TenantScope],
) -> None:
    url, scope = worker_scope
    factory = _factory(url)
    job = _create_job(factory, scope)
    handler = CountingHandler()
    worker = JobWorker(
        repository=JobRepository(),
        settings=WorkerSettings(worker_id="worker-a"),
        handlers={"research.run": handler},
    )
    repo = JobRepository()
    with transaction(factory, scope=scope) as session:
        repo.acquire_job(job.id, "worker-a", 30, session)
        repo.complete_job(job.id, "worker-a", {"status": "done"}, session)

    received = received_message_from_job(job)
    with transaction(factory, scope=scope) as session:
        disposition = worker.process_queue_message(received.message, session)
    assert disposition is MessageDisposition.ACK
    assert handler.calls == 0


def test_worker_crash_before_commit_leaves_job_queued(
    worker_scope: tuple[str, TenantScope],
) -> None:
    url, scope = worker_scope
    factory = _factory(url)
    job = _create_job(factory, scope, payload={"simulate": "raise"})
    worker = JobWorker(
        repository=JobRepository(),
        settings=WorkerSettings(worker_id="worker-a"),
        handlers={"research.run": ResearchRunStubHandler()},
    )
    received = received_message_from_job(job)
    with pytest.raises(RuntimeError):
        with factory.begin() as session:
            from sqlalchemy import text

            session.execute(
                text("SELECT set_config('app.tenant_id', :value, true)"),
                {"value": str(scope.tenant_id)},
            )
            session.execute(
                text("SELECT set_config('app.workspace_id', :value, true)"),
                {"value": str(scope.workspace_id)},
            )
            worker.process_queue_message(received.message, session)
            raise RuntimeError("crash before commit")

    with transaction(factory, scope=scope) as session:
        row = session.scalar(select(Job).where(Job.id == job.id))
        assert row is not None
        assert row.status == "queued"


def test_crash_after_commit_before_delete_reprocesses_as_ack(
    worker_scope: tuple[str, TenantScope],
) -> None:
    url, scope = worker_scope
    factory = _factory(url)
    job = _create_job(factory, scope)
    handler = CountingHandler()
    worker = JobWorker(
        repository=JobRepository(),
        settings=WorkerSettings(worker_id="worker-a"),
        handlers={"research.run": handler},
    )
    received = received_message_from_job(job)
    with transaction(factory, scope=scope) as session:
        assert worker.process_queue_message(received.message, session) is MessageDisposition.ACK
    assert handler.calls == 1

    with transaction(factory, scope=scope) as session:
        assert worker.process_queue_message(received.message, session) is MessageDisposition.ACK
    assert handler.calls == 1


def test_lease_contention_returns_nack(worker_scope: tuple[str, TenantScope]) -> None:
    url, scope = worker_scope
    factory = _factory(url)
    job = _create_job(factory, scope)
    repo = JobRepository()
    with transaction(factory, scope=scope) as session:
        repo.acquire_job(job.id, "worker-other", 30, session)

    worker = JobWorker(
        repository=JobRepository(),
        settings=WorkerSettings(worker_id="worker-a"),
        handlers={"research.run": ResearchRunStubHandler()},
    )
    received = received_message_from_job(job)
    with transaction(factory, scope=scope) as session:
        disposition = worker.process_queue_message(received.message, session)
    assert disposition is MessageDisposition.NACK


def test_cancellation_is_acknowledged_without_rerun(
    worker_scope: tuple[str, TenantScope],
) -> None:
    url, scope = worker_scope
    factory = _factory(url)
    job = _create_job(factory, scope)
    handler = CountingHandler()
    repo = JobRepository()
    with transaction(factory, scope=scope) as session:
        repo.request_cancellation(job.id, session)

    worker = JobWorker(
        repository=JobRepository(),
        settings=WorkerSettings(worker_id="worker-a"),
        handlers={"research.run": handler},
    )
    received = received_message_from_job(job)
    with transaction(factory, scope=scope) as session:
        assert worker.process_queue_message(received.message, session) is MessageDisposition.ACK
    assert handler.calls == 0


def test_heartbeat_extends_lease(worker_scope: tuple[str, TenantScope]) -> None:
    url, scope = worker_scope
    factory = _factory(url)
    fixed_now = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
    job = _create_job(factory, scope, payload={"simulate": "heartbeat"})
    worker = JobWorker(
        repository=JobRepository(),
        settings=WorkerSettings(worker_id="worker-a", lease_seconds=30),
        handlers={"research.run": ResearchRunStubHandler()},
        clock=lambda: fixed_now,
    )
    received = received_message_from_job(job)
    with transaction(factory, scope=scope) as session:
        worker.process_queue_message(received.message, session)
        row = session.scalar(select(Job).where(Job.id == job.id))
        assert row is not None
        assert row.leased_until is None
        assert row.status == "succeeded"


def test_retry_exhaustion_marks_job_failed(
    worker_scope: tuple[str, TenantScope],
) -> None:
    url, scope = worker_scope
    factory = _factory(url)
    job = _create_job(factory, scope, payload={"simulate": "retry"}, max_attempts=2)
    fixed_now = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
    worker = JobWorker(
        repository=JobRepository(),
        settings=WorkerSettings(worker_id="worker-a", retry_base_seconds=1, retry_max_seconds=1),
        handlers={"research.run": ResearchRunStubHandler()},
        clock=lambda: fixed_now,
        jitter=lambda _a, _b: 0.0,
    )
    received = received_message_from_job(job)

    with transaction(factory, scope=scope) as session:
        assert worker.process_queue_message(received.message, session) is MessageDisposition.ACK
        row = session.scalar(select(Job).where(Job.id == job.id))
        assert row is not None
        assert row.status == "queued"

    with transaction(factory, scope=scope) as session:
        row = session.scalar(select(Job).where(Job.id == job.id))
        assert row is not None
        row.available_at = fixed_now - timedelta(seconds=1)
        session.flush()

    with transaction(factory, scope=scope) as session:
        assert worker.process_queue_message(received.message, session) is MessageDisposition.ACK
        row = session.scalar(select(Job).where(Job.id == job.id))
        assert row is not None
        assert row.status == "failed"


def test_unknown_job_kind_fails_terminal(
    worker_scope: tuple[str, TenantScope],
) -> None:
    url, scope = worker_scope
    factory = _factory(url)
    job = _create_job(factory, scope, kind="unknown.kind")
    worker = JobWorker(
        repository=JobRepository(),
        settings=WorkerSettings(worker_id="worker-a"),
        handlers={"research.run": ResearchRunStubHandler()},
    )
    received = received_message_from_job(job)
    with transaction(factory, scope=scope) as session:
        assert worker.process_queue_message(received.message, session) is MessageDisposition.ACK
        row = session.scalar(select(Job).where(Job.id == job.id))
        assert row is not None
        assert row.status == "failed"
        assert row.error_code == "unknown_job_kind"


def test_runner_deletes_message_only_after_ack(
    worker_scope: tuple[str, TenantScope],
) -> None:
    url, scope = worker_scope
    factory = _factory(url)
    job = _create_job(factory, scope)
    received = received_message_from_job(job)
    consumer = StubSqsConsumer([received])
    runner = WorkerRunner(
        session_factory=factory,
        consumer=consumer,
        worker=JobWorker(
            repository=JobRepository(),
            settings=WorkerSettings(worker_id="worker-a"),
            handlers={"research.run": ResearchRunStubHandler()},
        ),
        settings=WorkerSettings(worker_id="worker-a"),
    )
    assert runner.run_once() is True
    assert consumer.deleted == [received.receipt_handle]
