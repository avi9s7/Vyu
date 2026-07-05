from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from src.vyu.db.models.tenancy import Membership
from src.vyu.db.repositories.tenancy import (
    NewMembership,
    NewTenant,
    NewWorkspace,
    TenancyRepository,
)
from src.vyu.db.session import TenantScope, build_engine, build_session_factory, transaction
from src.vyu.db.settings import DatabaseSettings


@pytest.fixture
def seeded_tenants(postgres_urls: dict[str, str]) -> dict[str, UUID]:
    from src.vyu.db.repositories.tenancy import IdentityUser

    tenant_a = uuid4()
    tenant_b = uuid4()
    workspace_a = uuid4()
    workspace_b = uuid4()
    user_a = uuid4()
    user_b = uuid4()
    migration_engine = build_engine(
        DatabaseSettings(database_url=postgres_urls["migration"])
    )
    factory = build_session_factory(migration_engine)
    with factory.begin() as session:
        repo = TenancyRepository(session)
        repo.add_tenant(NewTenant(id=tenant_a, slug="tenant-a", name="Tenant A"))
        repo.add_tenant(NewTenant(id=tenant_b, slug="tenant-b", name="Tenant B"))
        repo.add_workspace(
            NewWorkspace(id=workspace_a, tenant_id=tenant_a, slug="ws-a", name="WS A")
        )
        repo.add_workspace(
            NewWorkspace(id=workspace_b, tenant_id=tenant_b, slug="ws-b", name="WS B")
        )
        repo.upsert_user(
            IdentityUser(
                id=user_a,
                issuer="https://example.invalid",
                subject="user-a",
                email="a@example.invalid",
            )
        )
        repo.upsert_user(
            IdentityUser(
                id=user_b,
                issuer="https://example.invalid",
                subject="user-b",
                email="b@example.invalid",
            )
        )
        repo.add_membership(
            NewMembership(
                id=uuid4(),
                tenant_id=tenant_a,
                workspace_id=workspace_a,
                user_id=user_a,
                role="reviewer",
            )
        )
        repo.add_membership(
            NewMembership(
                id=uuid4(),
                tenant_id=tenant_b,
                workspace_id=workspace_b,
                user_id=user_b,
                role="reviewer",
            )
        )
    return {
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "workspace_a": workspace_a,
        "workspace_b": workspace_b,
    }


def test_rls_scopes_memberships(postgres_urls: dict[str, str], seeded_tenants: dict[str, UUID]) -> None:
    settings = DatabaseSettings(database_url=postgres_urls["app"])
    factory = build_session_factory(build_engine(settings))
    scope_a = TenantScope(
        tenant_id=seeded_tenants["tenant_a"],
        workspace_id=seeded_tenants["workspace_a"],
    )
    scope_b = TenantScope(
        tenant_id=seeded_tenants["tenant_b"],
        workspace_id=seeded_tenants["workspace_b"],
    )

    with transaction(factory, scope=scope_a) as session:
        visible = session.scalars(select(Membership)).all()
        assert [row.tenant_id for row in visible] == [seeded_tenants["tenant_a"]]

    with transaction(factory, scope=scope_b) as session:
        visible = session.scalars(select(Membership)).all()
        assert [row.tenant_id for row in visible] == [seeded_tenants["tenant_b"]]

    with transaction(factory) as session:
        assert session.scalars(select(Membership)).all() == []

    with transaction(factory, scope=scope_a) as session:
        with pytest.raises(DBAPIError):
            session.add(
                Membership(
                    id=uuid4(),
                    tenant_id=seeded_tenants["tenant_b"],
                    workspace_id=seeded_tenants["workspace_b"],
                    user_id=uuid4(),
                    role="reviewer",
                    status="active",
                )
            )
            session.flush()
