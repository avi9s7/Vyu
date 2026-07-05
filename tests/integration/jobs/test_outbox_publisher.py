from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError
from sqlalchemy import select

from src.vyu.db.session import TenantScope, build_engine, build_session_factory, transaction
from src.vyu.db.settings import DatabaseSettings
from src.vyu.jobs.models import OutboxEvent
from src.vyu.jobs.outbox import OutboxPublisher
from src.vyu.jobs.queue import QueueMessage, SqsQueue


class StubSqsClient:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []
        self.failures_remaining = 0

    def send_message(self, *, QueueUrl: str, MessageBody: str) -> dict[str, Any]:
        del QueueUrl
        if self.failures_remaining > 0:
            self.failures_remaining -= 1
            raise ClientError(
                {"Error": {"Code": "ServiceUnavailable", "Message": "temporary failure"}},
                "SendMessage",
            )
        payload = json.loads(MessageBody)
        self.messages.append(payload)
        return {"MessageId": f"sqs-{len(self.messages)}"}


def _factory(url: str):
    return build_session_factory(build_engine(DatabaseSettings(database_url=url)))


def _sample_payload(*, message_id: str | None = None, job_id: str | None = None) -> dict[str, object]:
    return {
        "schema_version": 1,
        "message_id": message_id or str(uuid4()),
        "job_id": job_id or str(uuid4()),
        "tenant_id": str(uuid4()),
        "workspace_id": str(uuid4()),
        "kind": "research.run",
        "attempt": 0,
        "created_at": datetime.now(tz=UTC).isoformat(),
    }


def _insert_outbox(
    factory,
    scope: TenantScope,
    *,
    payload: dict[str, object] | None = None,
) -> OutboxEvent:
    outbox_id = uuid4()
    with transaction(factory, scope=scope) as session:
        row = OutboxEvent(
            id=outbox_id,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
            topic="jobs",
            aggregate_type="job",
            aggregate_id=str(payload["job_id"] if payload else uuid4()),
            payload=payload or _sample_payload(message_id=str(outbox_id)),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return row


@pytest.fixture
def outbox_scope(postgres_urls: dict[str, str]) -> tuple[str, TenantScope]:
    tenant_id = uuid4()
    workspace_id = uuid4()
    return postgres_urls["migration"], TenantScope(tenant_id=tenant_id, workspace_id=workspace_id)


def test_publish_marks_outbox_published_and_sends_minimal_payload(
    outbox_scope: tuple[str, TenantScope],
) -> None:
    url, scope = outbox_scope
    factory = _factory(url)
    row = _insert_outbox(factory, scope)
    client = StubSqsClient()
    publisher = OutboxPublisher(
        queue=SqsQueue(queue_url="https://example.local/queue", client=client)
    )

    with transaction(factory, scope=scope) as session:
        result = publisher.publish_next(session)

    assert result.published is True
    assert result.outbox_id == str(row.id)
    assert len(client.messages) == 1
    assert set(client.messages[0]) == {
        "schema_version",
        "message_id",
        "job_id",
        "tenant_id",
        "workspace_id",
        "kind",
        "attempt",
        "created_at",
    }

    with transaction(factory, scope=scope) as session:
        stored = session.scalar(select(OutboxEvent).where(OutboxEvent.id == row.id))
        assert stored is not None
        assert stored.published_at is not None
        assert stored.last_error is None


def test_failed_send_records_error_and_leaves_unpublished(
    outbox_scope: tuple[str, TenantScope],
) -> None:
    url, scope = outbox_scope
    factory = _factory(url)
    row = _insert_outbox(factory, scope)
    client = StubSqsClient()
    client.failures_remaining = 1
    publisher = OutboxPublisher(
        queue=SqsQueue(queue_url="https://example.local/queue", client=client)
    )

    with transaction(factory, scope=scope) as session:
        result = publisher.publish_next(session)

    assert result.published is False
    with transaction(factory, scope=scope) as session:
        stored = session.scalar(select(OutboxEvent).where(OutboxEvent.id == row.id))
        assert stored is not None
        assert stored.published_at is None
        assert stored.attempt == 1
        assert stored.last_error


def test_unpublished_recovery_after_failure(
    outbox_scope: tuple[str, TenantScope],
) -> None:
    url, scope = outbox_scope
    factory = _factory(url)
    _insert_outbox(factory, scope)
    client = StubSqsClient()
    client.failures_remaining = 1
    publisher = OutboxPublisher(
        queue=SqsQueue(queue_url="https://example.local/queue", client=client)
    )

    with transaction(factory, scope=scope) as session:
        assert publisher.publish_next(session).published is False
    with transaction(factory, scope=scope) as session:
        assert publisher.publish_next(session).published is True
    assert len(client.messages) == 1


def test_no_publish_before_database_commit(outbox_scope: tuple[str, TenantScope]) -> None:
    url, scope = outbox_scope
    factory = _factory(url)
    client = StubSqsClient()
    publisher = OutboxPublisher(
        queue=SqsQueue(queue_url="https://example.local/queue", client=client)
    )
    outbox_id = uuid4()

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
        session.add(
            OutboxEvent(
                id=outbox_id,
                tenant_id=scope.tenant_id,
                workspace_id=scope.workspace_id,
                topic="jobs",
                aggregate_type="job",
                aggregate_id=str(uuid4()),
                payload=_sample_payload(message_id=str(outbox_id)),
            )
        )
        session.flush()
        with transaction(factory, scope=scope) as other_session:
            assert publisher.publish_next(other_session).published is False

    assert client.messages == []

    with transaction(factory, scope=scope) as session:
        assert publisher.publish_next(session).published is True
    assert len(client.messages) == 1


def test_duplicate_publisher_processes_each_event_once(
    outbox_scope: tuple[str, TenantScope],
) -> None:
    url, scope = outbox_scope
    factory = _factory(url)
    _insert_outbox(factory, scope)
    clients = [StubSqsClient(), StubSqsClient()]
    publishers = [
        OutboxPublisher(queue=SqsQueue(queue_url="https://example.local/queue", client=client))
        for client in clients
    ]

    def publish_once(publisher: OutboxPublisher) -> bool:
        with transaction(factory, scope=scope) as session:
            return publisher.publish_next(session).published

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(publish_once, publishers))

    assert sorted(results) == [False, True]
    total_messages = len(clients[0].messages) + len(clients[1].messages)
    assert total_messages == 1

    with transaction(factory, scope=scope) as session:
        unpublished = session.scalars(
            select(OutboxEvent).where(OutboxEvent.published_at.is_(None))
        ).all()
        published = session.scalars(
            select(OutboxEvent).where(OutboxEvent.published_at.isnot(None))
        ).all()
    assert len(unpublished) == 0
    assert len(published) == 1


def test_queue_message_rejects_extra_payload_fields() -> None:
    payload = _sample_payload()
    payload["question"] = "secret question text"
    with pytest.raises(ValueError, match="disallowed fields"):
        QueueMessage.from_payload(payload)
