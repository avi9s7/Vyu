from __future__ import annotations

from uuid import uuid4

import psycopg
import pytest

from src.vyu.db.repositories.audit import AuditRepository, DuplicateAuditEventError, NewAuditEvent
from src.vyu.db.repositories.tenancy import (
    NewTenant,
    NewWorkspace,
    TenancyRepository,
)
from src.vyu.db.session import TenantScope, build_engine, build_session_factory, transaction
from src.vyu.db.settings import DatabaseSettings


def test_audit_repository_append_only_and_scoped_list(postgres_urls: dict[str, str]) -> None:
    tenant_id = uuid4()
    workspace_id = uuid4()
    settings = DatabaseSettings(database_url=postgres_urls["migration"])
    factory = build_session_factory(build_engine(settings))
    scope = TenantScope(tenant_id=tenant_id, workspace_id=workspace_id)
    with factory.begin() as session:
        TenancyRepository(session).add_tenant(
            NewTenant(id=tenant_id, slug="audit-tenant", name="Audit Tenant")
        )
    with transaction(factory, scope=scope) as session:
        TenancyRepository(session).add_workspace(
            NewWorkspace(
                id=workspace_id, tenant_id=tenant_id, slug="audit-ws", name="Audit WS"
            )
        )

    app_settings = DatabaseSettings(database_url=postgres_urls["app"])
    app_factory = build_session_factory(build_engine(app_settings))
    event_id = uuid4()
    with transaction(app_factory, scope=scope) as session:
        audit = AuditRepository(session)
        record = audit.append(
            NewAuditEvent(
                id=event_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                actor_type="user",
                actor_id="operator-1",
                request_id="req-1",
                event_type="governance.import",
                resource_type="tenant",
                resource_id=str(tenant_id),
                outcome="success",
                payload_sha256="abc123",
            )
        )
        assert record.id == event_id
        with pytest.raises(DuplicateAuditEventError):
            audit.append(
                NewAuditEvent(
                    id=event_id,
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    actor_type="user",
                    actor_id="operator-1",
                    request_id="req-2",
                    event_type="governance.import",
                    resource_type="tenant",
                    resource_id=str(tenant_id),
                    outcome="success",
                    payload_sha256="abc123",
                )
            )
        listed = audit.list_for_resource(
            scope=scope, resource_type="tenant", resource_id=str(tenant_id)
        )
        assert len(listed) == 1

    psycopg_url = postgres_urls["app"].replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(psycopg_url) as connection, connection.cursor() as cursor:
        with pytest.raises(psycopg.errors.RaiseException):
            cursor.execute(
                "UPDATE audit_events SET outcome = 'tampered' WHERE id = %s",
                (str(event_id),),
            )
            connection.commit()
