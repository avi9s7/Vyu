from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from src.vyu.observability.config import ObservabilitySettings

_REDACTED = "[REDACTED]"


def _redact_value(key: str, value: Any, redacted_fields: set[str]) -> Any:
    normalized = key.replace("-", "_").lower()
    if normalized in redacted_fields or any(token in normalized for token in redacted_fields):
        return _REDACTED
    if isinstance(value, dict):
        return {child_key: _redact_value(child_key, child_value, redacted_fields) for child_key, child_value in value.items()}
    if isinstance(value, list):
        return [_redact_value(key, item, redacted_fields) for item in value]
    return value


class RedactingJsonFormatter(logging.Formatter):
    def __init__(self, settings: ObservabilitySettings) -> None:
        super().__init__()
        self._redacted_fields = {field.replace("-", "_").lower() for field in settings.redacted_field_names}

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "message",
            }:
                continue
            payload[key] = _redact_value(key, value, self._redacted_fields)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str, sort_keys=True)


def configure_structured_logging(settings: ObservabilitySettings | None = None) -> None:
    resolved = settings or ObservabilitySettings()
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    if resolved.log_json_enabled:
        handler.setFormatter(RedactingJsonFormatter(resolved))
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    root.addHandler(handler)
    root.setLevel(logging.INFO)
