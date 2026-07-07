from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from src.vyu.connectors.http import HttpClientError
from src.vyu.connectors.rate_limit import RateLimiter, StaticRateLimiter

T = TypeVar("T")

__all__ = ["ConnectorRuntime", "RateLimiter", "RetryPolicy", "RuntimeResult", "StaticRateLimiter"]


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    backoff_seconds: float = 0.25
    max_backoff_seconds: float = 8.0
    max_elapsed_seconds: float = 30.0
    jitter_ratio: float = 0.2
    retryable_exceptions: tuple[type[BaseException], ...] = (TimeoutError, ConnectionError)
    retryable_http_error_codes: frozenset[str] = frozenset(
        {"timeout", "connection_reset", "rate_limited", "server_error"}
    )

    @property
    def base_backoff_seconds(self) -> float:
        return self.backoff_seconds


@dataclass(frozen=True)
class RuntimeResult(Generic[T]):
    source: str
    action: str
    value: T
    attempts: int
    status: str
    elapsed_seconds: float = 0.0


class ConnectorRuntime:
    def __init__(
        self,
        retry_policy: RetryPolicy | None = None,
        rate_limiter: RateLimiter | None = None,
        sleep: Callable[[float], None] = time.sleep,
        randomizer: Callable[[], float] = random.random,
    ):
        self.retry_policy = retry_policy or RetryPolicy()
        self.rate_limiter = rate_limiter or StaticRateLimiter(max_calls=60, window_seconds=60)
        self.sleep = sleep
        self.randomizer = randomizer

    def run(self, source: str, action: str, operation: Callable[[], T]) -> RuntimeResult[T]:
        if not self.rate_limiter.allow(source):
            raise RuntimeError(f"Rate limit exceeded for connector {source!r}.")

        attempts = 0
        started_at = time.monotonic()
        while attempts < self.retry_policy.max_attempts:
            attempts += 1
            try:
                value = operation()
                return RuntimeResult(
                    source=source,
                    action=action,
                    value=value,
                    attempts=attempts,
                    status="ok",
                    elapsed_seconds=time.monotonic() - started_at,
                )
            except HttpClientError as exc:
                if not self._should_retry_http(exc, attempts, started_at):
                    raise
                self.sleep(self._backoff_seconds(exc, attempts))
            except self.retry_policy.retryable_exceptions:
                if attempts >= self.retry_policy.max_attempts or self._elapsed_exceeded(started_at):
                    raise
                self.sleep(self._backoff_seconds(None, attempts))

        raise RuntimeError(f"Connector operation {source}.{action} exited retry loop.")

    def _should_retry_http(
        self,
        exc: HttpClientError,
        attempts: int,
        started_at: float,
    ) -> bool:
        if exc.error_code not in self.retry_policy.retryable_http_error_codes:
            return False
        if attempts >= self.retry_policy.max_attempts:
            return False
        return not self._elapsed_exceeded(started_at)

    def _elapsed_exceeded(self, started_at: float) -> bool:
        return (time.monotonic() - started_at) >= self.retry_policy.max_elapsed_seconds

    def _backoff_seconds(self, exc: HttpClientError | None, attempts: int) -> float:
        if exc is not None and exc.retry_after_seconds is not None:
            return exc.retry_after_seconds
        exponential = min(
            self.retry_policy.base_backoff_seconds * (2 ** (attempts - 1)),
            self.retry_policy.max_backoff_seconds,
        )
        jitter = exponential * self.retry_policy.jitter_ratio * self.randomizer()
        return exponential + jitter
