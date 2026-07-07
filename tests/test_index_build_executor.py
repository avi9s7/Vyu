from __future__ import annotations

import unittest
from unittest.mock import MagicMock
from datetime import UTC, datetime
from uuid import uuid4

from src.vyu.jobs.contracts import JobRecord
from src.vyu.retrieval.builder import IndexBuildExecutor


class IndexBuildExecutorTests(unittest.TestCase):
    def test_simulate_retry_returns_retryable_result(self) -> None:
        executor = IndexBuildExecutor()
        now = datetime.now(tz=UTC)
        job = JobRecord(
            id=uuid4(),
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            kind="retrieval.index_build",
            status="running",
            attempt=1,
            max_attempts=3,
            payload={"simulate": "retry", "retrieval_index_id": str(uuid4())},
            result=None,
            error_code=None,
            available_at=now,
            leased_until=None,
            lease_owner="worker",
            created_at=now,
            updated_at=now,
            started_at=None,
            completed_at=None,
        )
        result = executor.execute(job, session=MagicMock(), heartbeat=lambda: None)
        self.assertEqual("retry", result.outcome)
        self.assertTrue(result.retryable)

    def test_missing_index_is_terminal_failure(self) -> None:
        executor = IndexBuildExecutor()
        session = MagicMock()
        session.scalar.return_value = None
        now = datetime.now(tz=UTC)
        job = JobRecord(
            id=uuid4(),
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            kind="retrieval.index_build",
            status="running",
            attempt=1,
            max_attempts=3,
            payload={"retrieval_index_id": str(uuid4())},
            result=None,
            error_code=None,
            available_at=now,
            leased_until=None,
            lease_owner="worker",
            created_at=now,
            updated_at=now,
            started_at=None,
            completed_at=None,
        )
        result = executor.execute(job, session=session, heartbeat=lambda: None)
        self.assertEqual("terminal_failure", result.outcome)
        self.assertEqual("retrieval_index_not_found", result.error_code)


if __name__ == "__main__":
    unittest.main()
