from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from src.vyu.api.app import create_app
from src.vyu.api.settings import ApiSettings


@pytest.fixture
def client() -> TestClient:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    settings = ApiSettings(
        git_sha="testsha123",
        env="test",
        image_digest="sha256:abc",
        expected_migration_revision="0004",
    )
    app = create_app(
        settings_override=settings,
        engine_override=engine,
        schema_revision_override="0004",
    )
    return TestClient(app, raise_server_exceptions=False)


def test_live_health(client: TestClient) -> None:
    response = client.get("/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"]


def test_ready_health_success(client: TestClient) -> None:
    response = client.get("/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_health_dependency_unavailable(client: TestClient) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    app = create_app(
        engine_override=engine,
        schema_revision_override="0004",
    )
    test_client = TestClient(app, raise_server_exceptions=False)
    with patch.object(engine, "connect", side_effect=OSError("database unavailable")):
        response = test_client.get("/v1/health/ready")
    assert response.status_code == 503
    payload = response.json()
    assert payload["error"]["code"] == "dependency_unavailable"
    assert payload["request_id"]


def test_version(client: TestClient) -> None:
    response = client.get("/v1/version")
    assert response.status_code == 200
    payload = response.json()
    assert payload["git_sha"] == "testsha123"
    assert payload["environment"] == "test"
    assert payload["image_digest"] == "sha256:abc"
    assert payload["schema_revision"] == "0003"
    assert "secret" not in response.text.lower()


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/v1/does-not-exist")
    assert response.status_code == 404
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "not_found"
    assert payload["request_id"]


def test_validation_error_envelope(client: TestClient) -> None:
    response = client.post("/v1/debug/validate", json={})
    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["fields"]
    assert payload["request_id"]
    assert payload["trace_id"]


def test_internal_error_hides_details(client: TestClient) -> None:
    response = client.get("/v1/debug/boom")
    assert response.status_code == 500
    payload = response.json()
    assert payload["error"]["code"] == "internal_error"
    assert "boom" not in response.text
