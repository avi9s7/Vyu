from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol


REQUIRED_MESSAGE_FIELDS = frozenset(
    {
        "schema_version",
        "message_id",
        "job_id",
        "tenant_id",
        "workspace_id",
        "kind",
        "attempt",
        "created_at",
    }
)


@dataclass(frozen=True)
class QueueMessage:
    schema_version: int
    message_id: str
    job_id: str
    tenant_id: str
    workspace_id: str
    kind: str
    attempt: int
    created_at: str

    def to_json(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "message_id": self.message_id,
            "job_id": self.job_id,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "kind": self.kind,
            "attempt": self.attempt,
            "created_at": self.created_at,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> QueueMessage:
        missing = REQUIRED_MESSAGE_FIELDS.difference(payload)
        if missing:
            raise ValueError(f"Outbox payload is missing required fields: {sorted(missing)}")
        extra = set(payload).difference(REQUIRED_MESSAGE_FIELDS)
        if extra:
            raise ValueError(f"Outbox payload contains disallowed fields: {sorted(extra)}")
        return cls(
            schema_version=int(payload["schema_version"]),  # type: ignore[arg-type]
            message_id=str(payload["message_id"]),
            job_id=str(payload["job_id"]),
            tenant_id=str(payload["tenant_id"]),
            workspace_id=str(payload["workspace_id"]),
            kind=str(payload["kind"]),
            attempt=int(payload["attempt"]),  # type: ignore[arg-type]
            created_at=str(payload["created_at"]),
        )


class SqsClient(Protocol):
    def send_message(self, *, QueueUrl: str, MessageBody: str) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class SqsQueue:
    queue_url: str
    client: SqsClient
    connect_timeout_seconds: float = 2.0
    read_timeout_seconds: float = 5.0
    max_attempts: int = 1

    def send(self, message: QueueMessage) -> str:
        response = self.client.send_message(
            QueueUrl=self.queue_url,
            MessageBody=json.dumps(message.to_json(), separators=(",", ":"), sort_keys=True),
        )
        message_id = response.get("MessageId")
        if not isinstance(message_id, str) or not message_id:
            raise RuntimeError("SQS send_message did not return MessageId.")
        return message_id


def build_boto3_sqs_client(
    *,
    connect_timeout_seconds: float,
    read_timeout_seconds: float,
    max_attempts: int,
    endpoint_url: str | None = None,
):
    import boto3
    from botocore.config import Config

    return boto3.client(
        "sqs",
        endpoint_url=endpoint_url,
        config=Config(
            connect_timeout=connect_timeout_seconds,
            read_timeout=read_timeout_seconds,
            retries={"max_attempts": max_attempts, "mode": "standard"},
        ),
    )
