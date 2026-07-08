from __future__ import annotations

import json
import random
import signal
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from src.vyu.db.session import TenantScope, tenant_scope_statements
from src.vyu.jobs.contracts import HandlerResult, JobRecord
from src.vyu.jobs.models import Job
from src.vyu.ingestion.handler import IngestionVerifyHandler
from src.vyu.ingestion.service import IngestionService
from src.vyu.ingestion.settings import IngestionSettings
from src.vyu.model_gateway.contracts import ModelPolicy
from src.vyu.model_gateway.gateway import ModelGateway
from src.vyu.research.executor import ResearchRunExecutor, ResearchRunHandler
from src.vyu.research.repository import ResearchExecutionRepository
from src.vyu.retrieval.builder import IndexBuildExecutor
from src.vyu.retrieval.handler import IndexBuildHandler
from src.vyu.synthesis.context import EvidenceContextBuilder
from src.vyu.synthesis.handler import SynthesisHandler
from src.vyu.synthesis.repository import ModelSynthesisRepository
from src.vyu.synthesis.service import SynthesisExecutor, SynthesisSettings
from src.vyu.jobs.queue import QueueMessage, ReceivedQueueMessage, SqsConsumer
from src.vyu.jobs.repository import JobRepository, TERMINAL_STATUSES


class MessageDisposition(StrEnum):
    ACK = "ack"
    NACK = "nack"


class JobHandler(Protocol):
    def handle(
        self,
        job: JobRecord,
        *,
        session: Session,
        heartbeat: Callable[[], None],
    ) -> HandlerResult:
        ...


@dataclass(frozen=True)
class WorkerSettings:
    worker_id: str = "vyu-worker"
    lease_seconds: int = 30
    retry_base_seconds: int = 2
    retry_max_seconds: int = 60
    stop_timeout_seconds: int = 30


@dataclass
class JobWorker:
    repository: JobRepository
    settings: WorkerSettings
    handlers: Mapping[str, JobHandler] = field(default_factory=dict)
    clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC)
    jitter: Callable[[float, float], float] = random.uniform

    def process_queue_message(
        self,
        message: QueueMessage,
        session: Session,
    ) -> MessageDisposition:
        scope = TenantScope(
            tenant_id=UUID(message.tenant_id),
            workspace_id=UUID(message.workspace_id),
        )
        for statement, parameters in tenant_scope_statements(scope):
            session.execute(statement, parameters)

        now = self.clock()
        job_id = UUID(message.job_id)
        job = self.repository.get_job(job_id, session)
        if job is None:
            return MessageDisposition.ACK

        if job.status in TERMINAL_STATUSES or job.status == "failed":
            return MessageDisposition.ACK

        if job.status == "queued" and job.available_at > now:
            return MessageDisposition.NACK

        lease = self.repository.acquire_job(
            job_id,
            self.settings.worker_id,
            self.settings.lease_seconds,
            session,
            now=now,
        )
        if lease is None:
            current = self.repository.get_job(job_id, session)
            if current is not None and current.status in TERMINAL_STATUSES | {"failed"}:
                return MessageDisposition.ACK
            return MessageDisposition.NACK

        def heartbeat() -> None:
            self.repository.extend_lease(
                job_id,
                self.settings.worker_id,
                self.settings.lease_seconds,
                session,
                now=self.clock(),
            )

        handler = self.handlers.get(job.kind)
        if handler is None:
            self.repository.fail_job(
                job_id,
                self.settings.worker_id,
                "unknown_job_kind",
                None,
                session,
                now=now,
            )
            return MessageDisposition.ACK

        refreshed = self.repository.get_job(job_id, session)
        if refreshed is not None and refreshed.status == "cancelled":
            return MessageDisposition.ACK

        try:
            result = handler.handle(job, session=session, heartbeat=heartbeat)
        except Exception:
            self.repository.fail_job(
                job_id,
                self.settings.worker_id,
                "handler_exception",
                self._retry_at(job.attempt + 1),
                session,
                now=self.clock(),
            )
            return MessageDisposition.ACK

        if result.outcome == "complete":
            self.repository.complete_job(
                job_id,
                self.settings.worker_id,
                result.result or {"status": "succeeded"},
                session,
                now=self.clock(),
            )
            return MessageDisposition.ACK

        if result.outcome == "retry" or result.retryable:
            self.repository.fail_job(
                job_id,
                self.settings.worker_id,
                result.error_code or "retryable_failure",
                self._retry_at(job.attempt + 1),
                session,
                now=self.clock(),
            )
            return MessageDisposition.ACK

        self.repository.fail_job(
            job_id,
            self.settings.worker_id,
            result.error_code or "terminal_failure",
            None,
            session,
            now=self.clock(),
        )
        return MessageDisposition.ACK

    def _retry_at(self, attempt: int) -> datetime | None:
        if attempt >= 1:
            delay = min(
                self.settings.retry_base_seconds * (2 ** max(attempt - 1, 0)),
                self.settings.retry_max_seconds,
            )
            jitter = self.jitter(0, delay * 0.1)
            return self.clock() + timedelta(seconds=delay + jitter)
        return self.clock() + timedelta(seconds=self.settings.retry_base_seconds)


@dataclass
class ResearchRunStubHandler:
    def handle(
        self,
        job: JobRecord,
        *,
        session: Session,
        heartbeat: Callable[[], None],
    ) -> HandlerResult:
        del session
        simulate = job.payload.get("simulate")
        if simulate == "heartbeat":
            heartbeat()
        if simulate == "retry":
            return HandlerResult(outcome="retry", error_code="transient", retryable=True)
        if simulate == "fail":
            return HandlerResult(outcome="terminal_failure", error_code="policy_blocked")
        if simulate == "raise":
            raise RuntimeError("simulated handler crash")
        return HandlerResult(outcome="complete", result={"status": "processed"})


@dataclass
class WorkerRunner:
    session_factory: sessionmaker[Session]
    consumer: SqsConsumer
    worker: JobWorker
    settings: WorkerSettings
    sleep: Callable[[float], None] = time.sleep
    _stop_requested: bool = field(default=False, init=False)

    def install_signal_handlers(self) -> None:
        def _handle_stop(signum: int, _frame: object) -> None:
            del signum
            self._stop_requested = True

        signal.signal(signal.SIGTERM, _handle_stop)
        signal.signal(signal.SIGINT, _handle_stop)

    def run_once(self) -> bool:
        messages = self.consumer.receive(max_messages=1)
        if not messages:
            return False
        for received in messages:
            disposition = self._process_received(received)
            if disposition is MessageDisposition.ACK:
                self.consumer.delete(received.receipt_handle)
        return True

    def run(self) -> int:
        self.install_signal_handlers()
        while not self._stop_requested:
            processed = self.run_once()
            if not processed:
                continue
        return 0

    def _process_received(self, received: ReceivedQueueMessage) -> MessageDisposition:
        with self.session_factory.begin() as session:
            return self.worker.process_queue_message(received.message, session)


def build_default_handlers(
    *,
    ingestion_service: IngestionService | None = None,
    research_executor: ResearchRunExecutor | None = None,
    index_build_executor: IndexBuildExecutor | None = None,
    synthesis_executor: SynthesisExecutor | None = None,
) -> dict[str, JobHandler]:
    ingestion = ingestion_service or IngestionService.from_settings(IngestionSettings())
    research = research_executor or ResearchRunExecutor()
    index_build = index_build_executor or IndexBuildExecutor()
    synthesis = synthesis_executor or SynthesisExecutor(
        gateway=ModelGateway(
            policy=ModelPolicy(
                policy_version="worker-default",
                allowed_providers=frozenset({"deterministic"}),
                allowed_models=frozenset({"vyu-deterministic-v1"}),
                allowed_use_cases=frozenset({"grounded_synthesis"}),
                allowed_prompt_versions=frozenset({"grounded_answer_v1"}),
            ),
            generation_adapters={},
            embedding_adapters={},
        ),
        repository=ModelSynthesisRepository(),
        research_repository=ResearchExecutionRepository(),
        context_builder=EvidenceContextBuilder(),
        settings=SynthesisSettings(),
    )
    return {
        "research.run": ResearchRunHandler(research),
        "ingestion.verify": IngestionVerifyHandler(ingestion),
        "retrieval.index_build": IndexBuildHandler(index_build),
        "synthesis.run": SynthesisHandler(synthesis),
    }


def message_from_job(job: Job, *, message_id: str | None = None) -> QueueMessage:
    return QueueMessage(
        schema_version=1,
        message_id=message_id or str(job.id),
        job_id=str(job.id),
        tenant_id=str(job.tenant_id),
        workspace_id=str(job.workspace_id),
        kind=job.kind,
        attempt=job.attempt,
        created_at=datetime.now(tz=UTC).isoformat(),
    )


def received_message_from_job(job: Job, *, receipt_handle: str | None = None) -> ReceivedQueueMessage:
    message = message_from_job(job)
    return ReceivedQueueMessage(
        receipt_handle=receipt_handle or f"receipt-{job.id}",
        message=message,
        sqs_message_id=f"sqs-{job.id}",
    )


def encode_received_body(message: QueueMessage) -> str:
    return json.dumps(message.to_json(), separators=(",", ":"), sort_keys=True)
