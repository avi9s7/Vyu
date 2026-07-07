from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Mapping
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from src.vyu.api.app import create_app
from src.vyu.api.settings import ApiSettings
from src.vyu.auth.settings import AuthSettings
from src.vyu.db.repositories.tenancy import (
    IdentityUser,
    NewMembership,
    NewTenant,
    NewWorkspace,
    TenancyRepository,
)
from src.vyu.db.session import TenantScope, build_engine, build_session_factory, transaction
from src.vyu.db.settings import DatabaseSettings


@dataclass(frozen=True)
class AuthTestContext:
    client: TestClient
    auth_settings: AuthSettings
    tenant_id: UUID
    workspace_id: UUID
    user_id: UUID
    issuer: str
    subject: str
    role: str


def mint_hs256_token(
    *,
    secret: str,
    issuer: str,
    audience: str,
    subject: str,
    tenant_id: str,
    workspace_id: str,
    email: str = "user@example.com",
    email_verified: bool = True,
    roles: tuple[str, ...] = ("vyu:admin",),
    exp: int | None = None,
) -> str:
    now = int(time.time())
    payload = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "exp": exp if exp is not None else now + 3600,
        "iat": now,
        "email": email,
        "email_verified": email_verified,
        "vyu": {
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
            "roles": list(roles),
        },
    }
    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = _b64_json(header)
    encoded_payload = _b64_json(payload)
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_payload}.{_b64(signature)}"


def seed_active_membership(
    factory: sessionmaker,
    *,
    tenant_id: UUID | None = None,
    workspace_id: UUID | None = None,
    user_id: UUID | None = None,
    issuer: str = "https://local.vyu.invalid",
    subject: str = "user-test-1",
    role: str = "reviewer",
) -> tuple[UUID, UUID, UUID]:
    tenant_id = tenant_id or uuid4()
    workspace_id = workspace_id or uuid4()
    scope = TenantScope(tenant_id=tenant_id, workspace_id=workspace_id)

    with factory.begin() as session:
        repo = TenancyRepository(session)
        repo.add_tenant(NewTenant(id=tenant_id, slug=f"tenant-{tenant_id.hex[:8]}", name="Test Tenant"))
        user = repo.upsert_user(
            IdentityUser(
                id=user_id or uuid4(),
                issuer=issuer,
                subject=subject,
                email="user@example.com",
                email_verified=True,
            )
        )
        user_id = user.id
    with transaction(factory, scope=scope) as session:
        repo = TenancyRepository(session)
        repo.add_workspace(
            NewWorkspace(
                id=workspace_id,
                tenant_id=tenant_id,
                slug=f"workspace-{workspace_id.hex[:8]}",
                name="Test Workspace",
            )
        )
        repo.add_membership(
            NewMembership(
                id=uuid4(),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                user_id=user_id,
                role=role,
            )
        )
    return tenant_id, workspace_id, user_id


def build_auth_test_client(
    postgres_urls: Mapping[str, str],
    *,
    role: str = "reviewer",
    subject: str | None = None,
) -> AuthTestContext:
    resolved_subject = subject or f"user-{uuid4()}"
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
    tenant_id, workspace_id, user_id = seed_active_membership(
        migration_factory,
        issuer=auth_settings.token_issuer,
        subject=resolved_subject,
        role=role,
    )
    app = create_app(
        settings_override=ApiSettings(env="test", expected_migration_revision="0004"),
        database_settings_override=app_settings,
        auth_settings_override=auth_settings,
        schema_revision_override="0004",
    )
    client = TestClient(app, raise_server_exceptions=False)
    return AuthTestContext(
        client=client,
        auth_settings=auth_settings,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        user_id=user_id,
        issuer=auth_settings.token_issuer,
        subject=resolved_subject,
        role=role,
    )


def bearer_token(context: AuthTestContext, **overrides: object) -> str:
    defaults = {
        "secret": context.auth_settings.hs256_secret,
        "issuer": context.issuer,
        "audience": context.auth_settings.token_audience,
        "subject": context.subject,
        "tenant_id": str(context.tenant_id),
        "workspace_id": str(context.workspace_id),
    }
    defaults.update(overrides)
    return mint_hs256_token(**defaults)  # type: ignore[arg-type]


def valid_research_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "question": "What is the efficacy of VX-101 for episodic migraine prevention?",
        "source_ids": ["pubmed"],
        "only_approved_sources": True,
    }
    payload.update(overrides)
    return payload


def auth_headers(context: AuthTestContext, *, idempotency_key: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {bearer_token(context)}"}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _b64_json(payload: Mapping[str, object]) -> str:
    return _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _b64(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
