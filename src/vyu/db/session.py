from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Engine, TextClause, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from src.vyu.db.settings import DatabaseSettings


@dataclass(frozen=True)
class TenantScope:
    tenant_id: UUID
    workspace_id: UUID


def build_engine(settings: DatabaseSettings) -> Engine:
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout_seconds,
        connect_args={
            "options": f"-c statement_timeout={settings.database_statement_timeout_ms}"
        },
        echo=settings.database_echo,
    )


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def tenant_scope_statements(scope: TenantScope) -> tuple[tuple[TextClause, dict[str, str]], ...]:
    return (
        (
            text("SELECT set_config('app.tenant_id', :value, true)"),
            {"value": str(scope.tenant_id)},
        ),
        (
            text("SELECT set_config('app.workspace_id', :value, true)"),
            {"value": str(scope.workspace_id)},
        ),
    )


@contextmanager
def transaction(
    factory: sessionmaker[Session],
    *,
    scope: TenantScope | None = None,
) -> Iterator[Session]:
    with factory.begin() as session:
        if scope is not None:
            for statement, parameters in tenant_scope_statements(scope):
                session.execute(statement, parameters)
        yield session
