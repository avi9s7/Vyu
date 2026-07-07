from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AdapterRetrySettings:
    max_attempts: int = 3
    retry_base_seconds: float = 0.5
    retry_max_seconds: float = 8.0


def backoff_seconds(attempt: int, *, settings: AdapterRetrySettings) -> float:
    return min(
        settings.retry_base_seconds * (2 ** max(attempt - 1, 0)),
        settings.retry_max_seconds,
    )


def retry_after_from_header(headers: object, header_name: str = "retry-after") -> float | None:
    getter = getattr(headers, "get", None)
    if getter is None:
        return None
    header = getter(header_name)
    if header is None:
        return None
    try:
        return max(float(header), 0.0)
    except (TypeError, ValueError):
        return None
