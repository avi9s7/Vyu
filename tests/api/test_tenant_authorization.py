from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from src.vyu.api.app import create_app
from src.vyu.api.settings import ApiSettings
from src.vyu.auth.settings import AuthSettings
from src.vyu.db.repositories.tenancy import IdentityUser, TenancyRepository
from src.vyu.db.session import build_engine, build_session_factory
from src.vyu.db.settings import DatabaseSettings
from tests.api.support import AuthTestContext, bearer_token, build_auth_test_client


def test_inactive_membership_returns_403(postgres_urls: dict[str, str]) -> None:
    auth_settings = AuthSettings(
        env="test",
        auth_mode="local_hs256",
        token_issuer="https://local.vyu.invalid",
        token_audience="vyu-local",
        hs256_secret="test-auth-secret",
        require_email_verified=True,
    )
    migration_settings = DatabaseSettings(database_url=postgres_urls["migration"])
    app_settings = DatabaseSettings(database_url=postgres_urls["app"])
    migration_factory = build_session_factory(build_engine(migration_settings))
    tenant_id = uuid4()
    workspace_id = uuid4()
    subject = "inactive-user"

    with migration_factory.begin() as session:
        repo = TenancyRepository(session)
        user = repo.upsert_user(
            IdentityUser(
                id=uuid4(),
                issuer=auth_settings.token_issuer,
                subject=subject,
                email="inactive@example.com",
                email_verified=True,
            )
        )
        user_id = user.id

    app = create_app(
        settings_override=ApiSettings(env="test", expected_migration_revision="0003"),
        database_settings_override=app_settings,
        auth_settings_override=auth_settings,
        schema_revision_override="0003",
    )
    client = TestClient(app, raise_server_exceptions=False)
    token = bearer_token(
        AuthTestContext(
            client=client,
            auth_settings=auth_settings,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=user_id,
            issuer=auth_settings.token_issuer,
            subject=subject,
            role="reviewer",
        )
    )
    response = client.get(
        "/v1/debug/whoami",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "authorization_failed"


def test_cross_tenant_resource_returns_404(postgres_urls: dict[str, str]) -> None:
    auth_context = build_auth_test_client(postgres_urls)
    token = bearer_token(auth_context)
    other_tenant_id = uuid4()
    response = auth_context.client.get(
        f"/v1/debug/tenant-resource/{other_tenant_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_claimed_admin_role_is_narrowed_to_stored_reviewer(
    postgres_urls: dict[str, str],
) -> None:
    auth_context = build_auth_test_client(postgres_urls, role="reviewer")
    token = bearer_token(auth_context, roles=("vyu:admin", "vyu:owner"))
    response = auth_context.client.get(
        "/v1/debug/whoami",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "reviewer"
