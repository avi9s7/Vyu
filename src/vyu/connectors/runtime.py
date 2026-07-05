from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Generic, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    backoff_seconds: float = 0.25
    retryable_exceptions: tuple[type[BaseException], ...] = (TimeoutError, ConnectionError)


@dataclass(frozen=True)
class RuntimeResult(Generic[T]):
    source: str
    action: str
    value: T
    attempts: int
    status: str


@dataclass
class StaticRateLimiter:
    max_calls: int
    window_seconds: float
    clock: Callable[[], float] = time.monotonic
    _calls: list[float] = field(default_factory=list)

    def allow(self) -> bool:
        now = self.clock()
        cutoff = now - self.window_seconds
        self._calls = [called_at for called_at in self._calls if called_at > cutoff]
        if len(self._calls) >= self.max_calls:
            return False
        self._calls.append(now)
        return True


class ConnectorRuntime:
    def __init__(
        self,
        retry_policy: RetryPolicy | None = None,
        rate_limiter: StaticRateLimiter | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.retry_policy = retry_policy or RetryPolicy()
        self.rate_limiter = rate_limiter or StaticRateLimiter(max_calls=60, window_seconds=60)
        self.sleep = sleep

    def run(self, source: str, action: str, operation: Callable[[], T]) -> RuntimeResult[T]:
        if not self.rate_limiter.allow():
            raise RuntimeError(f"Rate limit exceeded for connector {source!r}.")

        attempts = 0
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
                )
            except self.retry_policy.retryable_exceptions:
                if attempts >= self.retry_policy.max_attempts:
                    raise
                self.sleep(self.retry_policy.backoff_seconds)

        raise RuntimeError(f"Connector operation {source}.{action} exited retry loop.")
