from __future__ import annotations

import sys

from src.vyu.db.session import build_engine, build_session_factory
from src.vyu.db.settings import DatabaseSettings
from src.vyu.jobs.queue import SqsConsumer, build_boto3_sqs_client
from src.vyu.jobs.repository import JobRepository
from src.vyu.jobs.worker import JobWorker, WorkerRunner, WorkerSettings, build_default_handlers


def main() -> int:
    database_settings = DatabaseSettings()
    session_factory = build_session_factory(build_engine(database_settings))
    queue_url = _required_env("VYU_SQS_QUEUE_URL")
    worker_settings = WorkerSettings(
        worker_id=_required_env("VYU_WORKER_ID", default="vyu-worker"),
        lease_seconds=int(_required_env("VYU_WORKER_LEASE_SECONDS", default="30")),
        stop_timeout_seconds=int(_required_env("VYU_WORKER_STOP_TIMEOUT_SECONDS", default="30")),
    )
    client = build_boto3_sqs_client(
        connect_timeout_seconds=2.0,
        read_timeout_seconds=max(worker_settings.lease_seconds + 5, 20),
        max_attempts=1,
        endpoint_url=_optional_env("VYU_SQS_ENDPOINT_URL"),
    )
    consumer = SqsConsumer(
        queue_url=queue_url,
        client=client,
        visibility_timeout_seconds=worker_settings.lease_seconds,
    )
    worker = JobWorker(
        repository=JobRepository(),
        settings=worker_settings,
        handlers=build_default_handlers(),
    )
    runner = WorkerRunner(
        session_factory=session_factory,
        consumer=consumer,
        worker=worker,
        settings=worker_settings,
    )
    return runner.run()


def _required_env(name: str, *, default: str | None = None) -> str:
    import os

    value = os.environ.get(name, default)
    if not value:
        raise SystemExit(f"{name} is required.")
    return value


def _optional_env(name: str) -> str | None:
    import os

    value = os.environ.get(name)
    return value or None


if __name__ == "__main__":
    sys.exit(main())
