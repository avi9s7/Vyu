from __future__ import annotations

from uuid import uuid4

import pytest

from src.vyu.db.repositories.tenancy import (
    DuplicateRecordError,
    IdentityUser,
    NewMembership,
    NewTenant,
    NewWorkspace,
    TenancyRepository,
)
from src.vyu.db.session import TenantScope, build_engine, build_session_factory, transaction
from src.vyu.db.settings import DatabaseSettings


def test_tenancy_repository_uniqueness_and_active_membership(
    postgres_urls: dict[str, str],
) -> None:
    settings = DatabaseSettings(database_url=postgres_urls["migration"])
    factory = build_session_factory(build_engine(settings))
    tenant_id = uuid4()
    workspace_id = uuid4()
    user_id = uuid4()
    scope = TenantScope(tenant_id=tenant_id, workspace_id=workspace_id)

    with factory.begin() as session:
        repo = TenancyRepository(session)
        repo.add_tenant(NewTenant(id=tenant_id, slug="acme", name="Acme"))
        with pytest.raises(DuplicateRecordError):
            repo.add_tenant(NewTenant(id=uuid4(), slug="acme", name="Other"))
        repo.add_workspace(
            NewWorkspace(id=workspace_id, tenant_id=tenant_id, slug="research", name="Research")
        )
        with pytest.raises(DuplicateRecordError):
            repo.add_workspace(
                NewWorkspace(
                    id=uuid4(), tenant_id=tenant_id, slug="research", name="Duplicate"
                )
            )
        repo.upsert_user(
            IdentityUser(
                id=user_id,
                issuer="https://issuer.example",
                subject="user-1",
                email="user@example.invalid",
            )
        )
        repo.add_membership(
            NewMembership(
                id=uuid4(),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                user_id=user_id,
                role="reviewer",
            )
        )

    app_settings = DatabaseSettings(database_url=postgres_urls["app"])
    app_factory = build_session_factory(build_engine(app_settings))
    with transaction(app_factory, scope=scope) as session:
        membership = TenancyRepository(session).get_active_membership(
            user_id=user_id, scope=scope
        )
        assert membership is not None
        assert membership.role == "reviewer"

    other_scope = TenantScope(tenant_id=uuid4(), workspace_id=uuid4())
    with transaction(app_factory, scope=other_scope) as session:
        assert (
            TenancyRepository(session).get_active_membership(
                user_id=user_id, scope=other_scope
            )
            is None
        )
