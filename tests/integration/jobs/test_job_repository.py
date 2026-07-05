from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.vyu.db.session import TenantScope, build_engine, build_session_factory, transaction
from src.vyu.db.settings import DatabaseSettings
from src.vyu.jobs.contracts import (
    IdempotencyConflict,
    IdempotencyRequest,
    InvalidJobTransition,
    NewJob,
)
from src.vyu.jobs.models import Job
from src.vyu.jobs.repository import JobRepository


@pytest.fixture
def job_scope(postgres_urls: dict[str, str]) -> tuple[dict[str, str], TenantScope]:
    tenant_id = uuid4()
    workspace_id = uuid4()
    scope = TenantScope(tenant_id=tenant_id, workspace_id=workspace_id)
    return {
        "migration": postgres_urls["migration"],
        "tenant_id": str(tenant_id),
        "workspace_id": str(workspace_id),
    }, scope


def _factory(url: str):
    return build_session_factory(build_engine(DatabaseSettings(database_url=url)))


def _create_job(
    factory,
    scope: TenantScope,
    *,
    job_id=None,
    max_attempts: int = 3,
) -> JobRepository:
    job_id = job_id or uuid4()
    repo = JobRepository()
    with transaction(factory, scope=scope) as session:
        repo.create_job(
            NewJob(
                id=job_id,
                tenant_id=scope.tenant_id,
                workspace_id=scope.workspace_id,
                kind="research.run",
                payload={"step": "start"},
                max_attempts=max_attempts,
            ),
            session,
        )
    return job_id


def test_legal_job_transitions(job_scope: tuple[dict[str, str], TenantScope]) -> None:
    urls, scope = job_scope
    factory = _factory(urls["migration"])
    job_id = _create_job(factory, scope)
    repo = JobRepository()

    with transaction(factory, scope=scope) as session:
        lease = repo.acquire_job(job_id, "worker-a", 30, session)
        assert lease is not None
    with transaction(factory, scope=scope) as session:
        completed = repo.complete_job(job_id, "worker-a", {"ok": True}, session)
        assert completed.status == "succeeded"

    job_id = _create_job(factory, scope)
    with transaction(factory, scope=scope) as session:
        repo.acquire_job(job_id, "worker-b", 30, session)
    with transaction(factory, scope=scope) as session:
        failed = repo.fail_job(job_id, "worker-b", "transient", None, session)
        assert failed.status == "failed"

    job_id = _create_job(factory, scope)
    with transaction(factory, scope=scope) as session:
        cancelled = repo.request_cancellation(job_id, session)
        assert cancelled.status == "cancelled"


def test_failed_retry_requires_available_at(job_scope: tuple[dict[str, str], TenantScope]) -> None:
    urls, scope = job_scope
    factory = _factory(urls["migration"])
    job_id = _create_job(factory, scope, max_attempts=3)
    repo = JobRepository()

    with transaction(factory, scope=scope) as session:
        repo.acquire_job(job_id, "worker-a", 30, session)
        repo.fail_job(
            job_id,
            "worker-a",
            "transient",
            datetime.now(tz=UTC) + timedelta(minutes=1),
            session,
        )
    with transaction(factory, scope=scope) as session:
        row = session.scalar(select(Job).where(Job.id == job_id))
        assert row is not None
        assert row.status == "queued"
        assert row.available_at is not None


def test_invalid_transition_leaves_job_unchanged(
    job_scope: tuple[dict[str, str], TenantScope],
) -> None:
    urls, scope = job_scope
    factory = _factory(urls["migration"])
    job_id = _create_job(factory, scope)
    repo = JobRepository()

    with pytest.raises(InvalidJobTransition):
        with transaction(factory, scope=scope) as session:
            repo.complete_job(job_id, "worker-a", {"ok": True}, session)

    with transaction(factory, scope=scope) as session:
        row = session.scalar(select(Job).where(Job.id == job_id))
        assert row is not None
        assert row.status == "queued"


def test_idempotency_conflict(job_scope: tuple[dict[str, str], TenantScope]) -> None:
    urls, scope = job_scope
    factory = _factory(urls["migration"])
    repo = JobRepository()
    request_a = IdempotencyRequest(
        tenant_id=scope.tenant_id,
        actor_id="user-1",
        route="POST /v1/research/searches",
        key="idem-1",
        request_sha256=hashlib.sha256(b"body-a").hexdigest(),
        expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
    )
    request_b = IdempotencyRequest(
        tenant_id=scope.tenant_id,
        actor_id="user-1",
        route="POST /v1/research/searches",
        key="idem-1",
        request_sha256=hashlib.sha256(b"body-b").hexdigest(),
        expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
    )

    with transaction(factory, scope=scope) as session:
        repo.get_or_create_idempotent(
            request_a,
            lambda: ("research_run", str(uuid4()), 202),
            session,
        )
    with pytest.raises(IdempotencyConflict):
        with transaction(factory, scope=scope) as session:
            repo.get_or_create_idempotent(
                request_b,
                lambda: ("research_run", str(uuid4()), 202),
                session,
            )


def test_idempotency_reuse_returns_existing(
    job_scope: tuple[dict[str, str], TenantScope],
) -> None:
    urls, scope = job_scope
    factory = _factory(urls["migration"])
    repo = JobRepository()
    resource_id = str(uuid4())
    request = IdempotencyRequest(
        tenant_id=scope.tenant_id,
        actor_id="user-1",
        route="POST /v1/research/searches",
        key="idem-2",
        request_sha256=hashlib.sha256(json.dumps({"q": "test"}).encode()).hexdigest(),
        expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
    )

    with transaction(factory, scope=scope) as session:
        created = repo.get_or_create_idempotent(
            request,
            lambda: ("research_run", resource_id, 202),
            session,
        )
    with transaction(factory, scope=scope) as session:
        reused = repo.get_or_create_idempotent(
            request,
            lambda: ("research_run", str(uuid4()), 202),
            session,
        )
    assert created.created is True
    assert reused.created is False
    assert reused.resource_id == resource_id


def test_acquire_job_is_exclusive(job_scope: tuple[dict[str, str], TenantScope]) -> None:
    urls, scope = job_scope
    factory = _factory(urls["migration"])
    job_id = _create_job(factory, scope)

    def attempt(worker_id: str) -> str | None:
        repo = JobRepository()
        with transaction(factory, scope=scope) as session:
            lease = repo.acquire_job(job_id, worker_id, 30, session)
            return worker_id if lease is not None else None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, ("worker-a", "worker-b")))
    winners = [result for result in results if result is not None]
    assert len(winners) == 1
