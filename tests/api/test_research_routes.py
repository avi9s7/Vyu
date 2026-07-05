from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine

from src.vyu.api.app import create_app
from src.vyu.research.service import ResearchService
from src.vyu.research.settings import ResearchSettings
from src.vyu.sources import ProductionSourceRecord, SourceRegistry
from tests.api.support import (
    AuthTestContext,
    auth_headers,
    build_auth_test_client,
    valid_research_payload,
)


@pytest.fixture
def research_context(postgres_urls: dict[str, str]) -> AuthTestContext:
    return build_auth_test_client(postgres_urls)


def _submit_search(
    context: AuthTestContext,
    *,
    idempotency_key: str = "research-idem-1",
    payload: dict[str, object] | None = None,
):
    body = payload or valid_research_payload()
    return context.client.post(
        "/v1/research/searches",
        headers=auth_headers(context, idempotency_key=idempotency_key),
        json=body,
    )


def test_create_research_search_returns_202_with_links(research_context: AuthTestContext) -> None:
    response = _submit_search(research_context)
    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["search_id"]
    assert payload["job_id"]
    assert payload["links"]["self"].endswith(payload["search_id"])
    assert payload["links"]["events"].endswith("/events")


def test_duplicate_same_body_idempotency_returns_same_ids(research_context: AuthTestContext) -> None:
    first = _submit_search(research_context, idempotency_key="same-key")
    second = _submit_search(research_context, idempotency_key="same-key")
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["search_id"] == second.json()["search_id"]
    assert first.json()["job_id"] == second.json()["job_id"]


def test_conflicting_idempotency_body_returns_409(research_context: AuthTestContext) -> None:
    first = _submit_search(research_context, idempotency_key="conflict-key")
    second = _submit_search(
        research_context,
        idempotency_key="conflict-key",
        payload=valid_research_payload(
            question="How does VX-101 compare with standard therapy for migraine prevention?"
        ),
    )
    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "idempotency_conflict"


def test_invalid_date_range_returns_422(research_context: AuthTestContext) -> None:
    response = _submit_search(
        research_context,
        idempotency_key="bad-dates",
        payload=valid_research_payload(date_from="2026-01-01", date_to="2025-01-01"),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_unapproved_source_returns_422(postgres_urls: dict[str, str]) -> None:
    from fastapi.testclient import TestClient

    from src.vyu.api.settings import ApiSettings
    from src.vyu.auth.settings import AuthSettings
    from src.vyu.db.settings import DatabaseSettings

    draft_registry = SourceRegistry(
        [
            ProductionSourceRecord(
                source_id="draft_source",
                display_name="Draft Source",
                source_type="public_literature",
                owner="Vyu",
                license_or_terms="test",
                allowed_uses=["literature_search"],
                approval_status="draft",
            )
        ]
    )
    context = build_auth_test_client(postgres_urls)
    app = create_app(
        settings_override=ApiSettings(env="test", expected_migration_revision="0003"),
        database_settings_override=DatabaseSettings(database_url=postgres_urls["app"]),
        auth_settings_override=AuthSettings(
            env="test",
            auth_mode="local_hs256",
            token_issuer=context.issuer,
            token_audience="vyu-local",
            hs256_secret="test-auth-secret",
            require_email_verified=True,
        ),
        schema_revision_override="0003",
        research_service_override=ResearchService(
            settings=ResearchSettings(env="test"),
            source_registry=draft_registry,
        ),
    )
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/v1/research/searches",
        headers=auth_headers(context, idempotency_key="draft-source"),
        json=valid_research_payload(source_ids=["draft_source"], only_approved_sources=True),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_cross_tenant_lookup_returns_404(postgres_urls: dict[str, str]) -> None:
    owner = build_auth_test_client(postgres_urls, subject="owner-user")
    created = _submit_search(owner, idempotency_key="owner-search")
    search_id = created.json()["search_id"]

    other = build_auth_test_client(postgres_urls, subject="other-user")
    response = other.client.get(
        f"/v1/research/searches/{search_id}",
        headers=auth_headers(other),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_cancel_sets_cancel_requested_and_emits_event(research_context: AuthTestContext) -> None:
    created = _submit_search(research_context, idempotency_key="cancel-me")
    search_id = created.json()["search_id"]
    cancel = research_context.client.post(
        f"/v1/research/searches/{search_id}/cancel",
        headers=auth_headers(research_context),
    )
    assert cancel.status_code == 200
    assert cancel.json()["cancel_requested"] is True

    detail = research_context.client.get(
        f"/v1/research/searches/{search_id}",
        headers=auth_headers(research_context),
    )
    assert detail.json()["cancel_requested"] is True

    events = research_context.client.get(
        f"/v1/research/searches/{search_id}/events",
        headers=auth_headers(research_context),
    )
    sequences = [item["sequence"] for item in events.json()["items"]]
    event_types = [item["event_type"] for item in events.json()["items"]]
    assert sequences == sorted(sequences)
    assert sequences[0] == 1
    assert "research_search_cancel_requested" in event_types


def test_openapi_contains_research_routes() -> None:
    app = create_app(
        engine_override=create_engine("sqlite+pysqlite:///:memory:"),
        schema_revision_override="0003",
    )
    schema = app.openapi()
    paths = schema["paths"]
    assert "/v1/research/searches" in paths
    assert "post" in paths["/v1/research/searches"]
    assert "/v1/research/searches/{search_id}" in paths
    assert "/v1/research/searches/{search_id}/events" in paths
    assert "/v1/research/searches/{search_id}/cancel" in paths
    component_names = set(schema.get("components", {}).get("schemas", {}))
    assert "CreateResearchSearchRequest" in component_names
    assert "ResearchSearchCreatedResponse" in component_names


def test_export_openapi_writes_document(tmp_path: Path) -> None:
    output = tmp_path / "openapi.json"
    schema = create_app(
        engine_override=create_engine("sqlite+pysqlite:///:memory:"),
        schema_revision_override="0003",
    ).openapi()
    output.write_text(__import__("json").dumps(schema, indent=2) + "\n", encoding="utf-8")
    assert output.exists()
    assert "/v1/research/searches" in schema["paths"]
