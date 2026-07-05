from __future__ import annotations

from uuid import UUID

from sqlalchemy import create_mock_engine

from src.vyu.db.session import TenantScope, tenant_scope_statements


def test_tenant_scope_statements_use_transaction_local_settings() -> None:
    scope = TenantScope(
        tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        workspace_id=UUID("22222222-2222-2222-2222-222222222222"),
    )
    statements = tenant_scope_statements(scope)
    assert [statement[1] for statement in statements] == [
        {"value": str(scope.tenant_id)},
        {"value": str(scope.workspace_id)},
    ]
    assert all("set_config" in str(statement[0]) for statement in statements)


def test_mock_engine_can_be_constructed_without_connecting() -> None:
    engine = create_mock_engine(
        "postgresql+psycopg://user:password@localhost/vyu",
        lambda *_args, **_kwargs: None,
    )
    assert engine.dialect.name == "postgresql"
