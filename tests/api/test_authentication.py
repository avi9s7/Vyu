from __future__ import annotations

import time

import pytest

from src.vyu.auth.settings import AuthSettings
from tests.api.support import AuthTestContext, bearer_token


def test_missing_bearer_token_returns_401(auth_context: AuthTestContext) -> None:
    response = auth_context.client.get("/v1/debug/whoami")
    assert response.status_code == 401
    payload = response.json()
    assert payload["error"]["code"] == "authentication_failed"
    assert payload["request_id"]


def test_invalid_bearer_token_returns_401(auth_context: AuthTestContext) -> None:
    response = auth_context.client.get(
        "/v1/debug/whoami",
        headers={"Authorization": "Bearer not-a-valid-token"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"


def test_expired_bearer_token_returns_401(auth_context: AuthTestContext) -> None:
    token = bearer_token(auth_context, exp=int(time.time()) - 60)
    response = auth_context.client.get(
        "/v1/debug/whoami",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"


def test_unverified_email_returns_401(auth_context: AuthTestContext) -> None:
    token = bearer_token(auth_context, email_verified=False)
    response = auth_context.client.get(
        "/v1/debug/whoami",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"


def test_valid_token_with_membership_returns_principal(auth_context: AuthTestContext) -> None:
    token = bearer_token(auth_context)
    response = auth_context.client.get(
        "/v1/debug/whoami",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["user_id"] == str(auth_context.user_id)
    assert payload["tenant_id"] == str(auth_context.tenant_id)
    assert payload["workspace_id"] == str(auth_context.workspace_id)
    assert payload["role"] == auth_context.role
    assert payload["authentication_method"] == "local_hs256"


def test_local_hs256_rejected_in_production() -> None:
    with pytest.raises(ValueError, match="local_hs256 auth mode is not allowed"):
        AuthSettings(env="production", auth_mode="local_hs256")


def test_health_live_does_not_require_authentication(auth_context: AuthTestContext) -> None:
    response = auth_context.client.get("/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
