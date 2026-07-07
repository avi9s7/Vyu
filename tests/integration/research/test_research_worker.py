from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from scripts.import_source_policy import import_policies
from src.vyu.db.session import TenantScope, build_engine, build_session_factory, transaction
from src.vyu.db.settings import DatabaseSettings
from src.vyu.jobs.contracts import NewJob
from src.vyu.jobs.models import Job, ResearchRun, ResearchRunEvent
from src.vyu.jobs.repository import JobRepository
from src.vyu.jobs.worker import JobWorker, WorkerSettings, received_message_from_job
from src.vyu.research.executor import ResearchRunHandler
from src.vyu.research.models import ResearchToolCallRow


@pytest.fixture
def research_factory(postgres_urls: dict[str, str]):
    return build_session_factory(
        build_engine(DatabaseSettings(database_url=postgres_urls["migration"]))
    )


def _seed_policy() -> None:
    import_policies(
        source_registry_path=__import__("pathlib").Path("config/source_registry.example.json"),
        tool_registry_path=__import__("pathlib").Path("config/research_tool_registry.example.json"),
        actor_id="research-worker-test",
        apply=True,
    )


def test_research_worker_executes_run_with_persisted_plan_and_tool_calls(research_factory) -> None:
    _seed_policy()
    scope = TenantScope(tenant_id=uuid4(), workspace_id=uuid4())
    run_id = uuid4()
    job_id = uuid4()
    repo = JobRepository()
    with transaction(research_factory, scope=scope) as session:
        session.add(
            ResearchRun(
                id=run_id,
                tenant_id=scope.tenant_id,
                workspace_id=scope.workspace_id,
                created_by=uuid4(),
                question="What is the efficacy of aspirin?",
                intended_use="literature_search",
                requested_sources=["pubmed"],
                status="queued",
                cancel_requested=False,
                policy_version="test",
            )
        )
        repo.create_job(
            NewJob(
                id=job_id,
                tenant_id=scope.tenant_id,
                workspace_id=scope.workspace_id,
                kind="research.run",
                payload={
                    "research_run_id": str(run_id),
                    "question": "What is the efficacy of aspirin?",
                    "source_ids": ["pubmed"],
                    "intended_use": "literature_search",
                    "only_approved_sources": True,
                },
            ),
            session,
        )
        job_row = session.scalar(select(Job).where(Job.id == job_id))
        assert job_row is not None

    worker = JobWorker(
        repository=repo,
        settings=WorkerSettings(worker_id="research-worker"),
        handlers={"research.run": ResearchRunHandler()},
    )
    with transaction(research_factory, scope=scope) as session:
        job_row = session.scalar(select(Job).where(Job.id == job_id))
        disposition = worker.process_queue_message(
            received_message_from_job(job_row).message,
            session,
        )
        session.flush()
        refreshed_run = session.scalar(select(ResearchRun).where(ResearchRun.id == run_id))
        events = session.scalars(
            select(ResearchRunEvent)
            .where(ResearchRunEvent.research_run_id == run_id)
            .order_by(ResearchRunEvent.sequence.asc())
        ).all()
        tool_calls = session.scalars(
            select(ResearchToolCallRow).where(ResearchToolCallRow.research_run_id == run_id)
        ).all()

    assert disposition.value == "ack"
    assert refreshed_run is not None
    assert refreshed_run.status == "completed"
    event_types = [event.event_type for event in events]
    assert "research_planning_started" in event_types
    assert "research_plan_persisted" in event_types
    assert "research_searching" in event_types
    assert "research_source_completed" in event_types
    assert len(tool_calls) >= 1


def test_duplicate_job_delivery_reuses_persisted_tool_calls(research_factory) -> None:
    _seed_policy()
    scope = TenantScope(tenant_id=uuid4(), workspace_id=uuid4())
    run_id = uuid4()
    job_id = uuid4()
    repo = JobRepository()
    with transaction(research_factory, scope=scope) as session:
        session.add(
            ResearchRun(
                id=run_id,
                tenant_id=scope.tenant_id,
                workspace_id=scope.workspace_id,
                created_by=uuid4(),
                question="aspirin migraine",
                intended_use="literature_search",
                requested_sources=["pubmed"],
                status="queued",
                cancel_requested=False,
                policy_version="test",
            )
        )
        repo.create_job(
            NewJob(
                id=job_id,
                tenant_id=scope.tenant_id,
                workspace_id=scope.workspace_id,
                kind="research.run",
                payload={
                    "research_run_id": str(run_id),
                    "question": "aspirin migraine",
                    "source_ids": ["pubmed"],
                    "intended_use": "literature_search",
                    "only_approved_sources": True,
                },
            ),
            session,
        )
        job_row = session.scalar(select(Job).where(Job.id == job_id))

    worker = JobWorker(
        repository=repo,
        settings=WorkerSettings(worker_id="research-worker"),
        handlers={"research.run": ResearchRunHandler()},
    )
    with transaction(research_factory, scope=scope) as session:
        job_row = session.scalar(select(Job).where(Job.id == job_id))
        worker.process_queue_message(received_message_from_job(job_row).message, session)
        first_count = len(
            session.scalars(
                select(ResearchToolCallRow).where(ResearchToolCallRow.research_run_id == run_id)
            ).all()
        )
        job_row.status = "queued"
        session.flush()
        worker.process_queue_message(received_message_from_job(job_row).message, session)
        second_count = len(
            session.scalars(
                select(ResearchToolCallRow).where(ResearchToolCallRow.research_run_id == run_id)
            ).all()
        )

    assert first_count >= 1
    assert second_count == first_count
