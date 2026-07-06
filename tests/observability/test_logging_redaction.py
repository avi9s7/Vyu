import logging

from src.vyu.observability.config import ObservabilitySettings
from src.vyu.observability.logging import RedactingJsonFormatter


def test_json_formatter_redacts_sensitive_fields() -> None:
    formatter = RedactingJsonFormatter(
        ObservabilitySettings(redacted_field_names=("authorization", "request_body"))
    )
    record = logging.LogRecord(
        name="vyu.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request received",
        args=(),
        exc_info=None,
    )
    record.authorization = "Bearer secret-token"
    record.request_body = "prompt text"

    payload = formatter.format(record)

    assert "secret-token" not in payload
    assert "prompt text" not in payload
    assert "[REDACTED]" in payload
