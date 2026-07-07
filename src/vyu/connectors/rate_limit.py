from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from src.vyu.db.session import transaction


class RateLimiter(Protocol):
    def allow(self, source: str) -> bool:
        ...


@dataclass
class StaticRateLimiter:
    """Process-local limiter for tests and local development only."""

    max_calls: int
    window_seconds: float
    clock: Callable[[], float] = time.monotonic
    _calls: list[float] = field(default_factory=list)

    def allow(self, source: str) -> bool:
        del source
        now = self.clock()
        cutoff = now - self.window_seconds
        self._calls = [called_at for called_at in self._calls if called_at > cutoff]
        if len(self._calls) >= self.max_calls:
            return False
        self._calls.append(now)
        return True


class PostgresRateLimiter:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        max_calls: int,
        window_seconds: float,
        clock: Callable[[], float] = time.time,
    ):
        self.session_factory = session_factory
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.clock = clock

    def allow(self, source: str) -> bool:
        window_start = int(self.clock() // self.window_seconds) * int(self.window_seconds)
        with transaction(self.session_factory) as session:
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:source_key))"),
                {"source_key": source},
            )
            row = session.execute(
                text(
                    """
                    INSERT INTO connector_rate_windows (source_key, window_start, call_count)
                    VALUES (:source_key, to_timestamp(:window_start), 1)
                    ON CONFLICT (source_key, window_start)
                    DO UPDATE SET call_count = connector_rate_windows.call_count + 1
                    RETURNING call_count
                    """
                ),
                {"source_key": source, "window_start": window_start},
            ).one()
            return int(row.call_count) <= self.max_calls
