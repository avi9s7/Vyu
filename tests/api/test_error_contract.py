from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from src.vyu.api.app import create_app


def test_error_envelope_shape() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    client = TestClient(
        create_app(engine_override=engine, schema_revision_override="0004"),
        raise_server_exceptions=False,
    )
    response = client.get("/v1/missing")
    payload = response.json()
    assert set(payload.keys()) == {"request_id", "trace_id", "status", "error"}
    assert set(payload["error"].keys()) >= {"code", "message", "retryable", "fields"}
