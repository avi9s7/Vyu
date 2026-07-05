# VYU PostgreSQL Persistence and Tenancy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce PostgreSQL, Alembic, focused repositories, and enforced tenant/workspace isolation while keeping current SQLite POC behavior available during migration.

**Architecture:** PostgreSQL becomes the production system of record. SQLAlchemy 2 provides synchronous transaction/repository boundaries, Alembic owns all DDL, and PostgreSQL row-level security adds defense in depth to application authorization. This plan creates identity, tenancy, audit, and migration foundations; later plans add their own subsystem tables through new Alembic revisions.

**Tech Stack:** Python 3.13, SQLAlchemy 2, Psycopg 3, Alembic, Pydantic Settings, PostgreSQL 17, pgvector 0.8, Docker Compose, pytest.

---

## Entry Gate

- Plan 1 is `complete` in `docs/production/IMPLEMENTATION_STATUS.md`.
- `uv run python scripts/verify.py --scope all` passes from a clean clone.
- Docker Desktop is running.

Read the current contracts before editing:

- `src/vyu/storage/production.py`
- `src/vyu/authz/__init__.py`
- `src/vyu/authz/tenant_governance.py`
- `src/vyu/authn/identity.py`
- `config/tenant_governance.local.example.json`
- `tests/test_tenant_governance.py`
- `tests/test_production_storage.py`

Do not add methods to `src/vyu/storage/production.py` in this plan.

## Planned File Map

| Path | Responsibility |
| --- | --- |
| `compose.yaml` | Local PostgreSQL service |
| `.env.example` | Safe local database settings |
| `src/vyu/db/settings.py` | Validated database configuration |
| `src/vyu/db/session.py` | Engine, transaction, and tenant-scope context |
| `src/vyu/db/models/base.py` | SQLAlchemy base and shared UUID/timestamp helpers |
| `src/vyu/db/models/tenancy.py` | Tenant, workspace, user, membership models |
| `src/vyu/db/models/audit.py` | Append-only audit-event model |
| `src/vyu/db/repositories/tenancy.py` | Focused tenancy persistence interface |
| `src/vyu/db/repositories/audit.py` | Focused append-only audit interface |
| `alembic.ini` | Alembic CLI configuration |
| `src/vyu/migrations/env.py` | Migration environment |
| `src/vyu/migrations/versions/0001_tenancy_audit.py` | Initial production schema and RLS |
| `scripts/import_tenant_registry.py` | Idempotent JSON registry import |
| `tests/integration/db/` | PostgreSQL migration, RLS, and repository tests |

## Task 1: Start a Pinned Local PostgreSQL Service

**Files:**

- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `compose.yaml`
- Create: `.env.example`
- Create: `tests/test_local_postgres_contract.py`

- [ ] **Step 1: Write the failing local-service contract test**

Create `tests/test_local_postgres_contract.py`:

```python
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LocalPostgresContractTests(unittest.TestCase):
    def test_compose_pins_postgres_and_declares_healthcheck(self) -> None:
        text = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        self.assertIn("pgvector/pgvector:0.8.0-pg17", text)
        self.assertIn("pg_isready", text)
        self.assertIn("vyu-postgres-data", text)

    def test_example_uses_postgresql_not_sqlite(self) -> None:
        text = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("VYU_DATABASE_URL=postgresql+psycopg://", text)
        self.assertNotIn("sqlite", text.lower())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Verify the contract fails because files are absent**

```powershell
uv run python -m unittest tests.test_local_postgres_contract -v
```

Expected: `FileNotFoundError` for `compose.yaml` or `.env.example`.

- [ ] **Step 3: Add database dependencies**

Add to `[project].dependencies` in `pyproject.toml`:

```toml
dependencies = [
  "alembic>=1.14,<2",
  "psycopg[binary,pool]>=3.2,<4",
  "pydantic-settings>=2.7,<3",
  "sqlalchemy>=2.0,<3",
]
```

Add to the `dev` dependency group:

```toml
  "testcontainers[postgres]>=4.9,<5",
```

Run:

```powershell
uv lock
uv sync --all-groups --frozen
```

Expected: the lock updates once, then frozen sync makes no changes.

- [ ] **Step 4: Create `compose.yaml`**

```yaml
name: vyu

services:
  postgres:
    image: pgvector/pgvector:0.8.0-pg17
    environment:
      POSTGRES_DB: vyu
      POSTGRES_USER: vyu_app
      POSTGRES_PASSWORD: local-vyu-password
    ports:
      - "127.0.0.1:5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U vyu_app -d vyu"]
      interval: 2s
      timeout: 2s
      retries: 30
    volumes:
      - vyu-postgres-data:/var/lib/postgresql/data

volumes:
  vyu-postgres-data:
```

The local password is intentionally non-secret and local-only. No staging or production deployment reads this file.

- [ ] **Step 5: Create `.env.example`**

```dotenv
VYU_ENV=local
VYU_DATABASE_URL=postgresql+psycopg://vyu_app:local-vyu-password@127.0.0.1:5432/vyu
VYU_DATABASE_POOL_SIZE=5
VYU_DATABASE_MAX_OVERFLOW=5
VYU_DATABASE_POOL_TIMEOUT_SECONDS=10
VYU_DATABASE_STATEMENT_TIMEOUT_MS=30000
VYU_DATABASE_ECHO=false
```

- [ ] **Step 6: Start and verify PostgreSQL**

```powershell
docker compose up -d postgres
docker compose ps postgres
docker compose exec postgres psql -U vyu_app -d vyu -c "SELECT version();"
docker compose exec postgres psql -U vyu_app -d vyu -c "CREATE EXTENSION IF NOT EXISTS vector; SELECT extversion FROM pg_extension WHERE extname = 'vector';"
uv run python -m unittest tests.test_local_postgres_contract -v
```

Expected: service is healthy, PostgreSQL reports major version 17, pgvector reports `0.8.0`, and two contract tests pass.

- [ ] **Step 7: Commit the local database boundary**

```powershell
git add pyproject.toml uv.lock compose.yaml .env.example tests/test_local_postgres_contract.py
git commit -m "build: add local PostgreSQL development service"
```

## Task 2: Add Validated Database Settings and Transactions

**Files:**

- Create: `src/vyu/db/__init__.py`
- Create: `src/vyu/db/settings.py`
- Create: `src/vyu/db/session.py`
- Create: `tests/unit/db/test_settings.py`
- Create: `tests/unit/db/test_session.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write failing settings tests**

Create `tests/unit/db/test_settings.py`:

```python
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.vyu.db.settings import DatabaseSettings


def test_database_settings_accept_postgresql() -> None:
    settings = DatabaseSettings(
        database_url="postgresql+psycopg://user:password@db.example/vyu",
        database_pool_size=8,
        database_max_overflow=4,
        database_pool_timeout_seconds=7,
        database_statement_timeout_ms=15_000,
        database_echo=False,
    )
    assert settings.database_pool_size == 8


def test_database_settings_reject_sqlite_for_production() -> None:
    with pytest.raises(ValidationError, match="PostgreSQL"):
        DatabaseSettings(
            env="production",
            database_url="sqlite:///production.sqlite",
        )
```

Create `tests/unit/db/test_session.py`:

```python
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
```

- [ ] **Step 2: Verify imports fail**

```powershell
uv run pytest tests/unit/db/test_settings.py tests/unit/db/test_session.py -q
```

Expected: import error for `src.vyu.db.settings`.

- [ ] **Step 3: Implement database settings**

Create `src/vyu/db/settings.py`:

```python
from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VYU_",
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "local"
    database_url: str = "postgresql+psycopg://vyu_app:local-vyu-password@127.0.0.1:5432/vyu"
    database_pool_size: int = Field(default=5, ge=1, le=100)
    database_max_overflow: int = Field(default=5, ge=0, le=100)
    database_pool_timeout_seconds: int = Field(default=10, ge=1, le=120)
    database_statement_timeout_ms: int = Field(default=30_000, ge=1_000, le=300_000)
    database_echo: bool = False

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str, info: object) -> str:
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError("VYU database URL must use PostgreSQL with Psycopg")
        return value
```

Production rejects SQLite unconditionally; local SQLite POC code remains accessed through its old explicit constructors, not through `DatabaseSettings`.

- [ ] **Step 4: Implement transaction and tenant scope helpers**

Create `src/vyu/db/session.py`:

```python
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Engine, create_engine, text
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


def tenant_scope_statements(scope: TenantScope) -> tuple[tuple[object, dict[str, str]], ...]:
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
```

Create `src/vyu/db/__init__.py`:

```python
from src.vyu.db.session import (
    TenantScope,
    build_engine,
    build_session_factory,
    transaction,
)
from src.vyu.db.settings import DatabaseSettings

__all__ = [
    "DatabaseSettings",
    "TenantScope",
    "build_engine",
    "build_session_factory",
    "transaction",
]
```

- [ ] **Step 5: Add new typed packages to mypy and verify**

Change mypy `files` in `pyproject.toml` to:

```toml
files = ["src/vyu/db", "scripts/verify.py"]
```

Run:

```powershell
uv run pytest tests/unit/db/test_settings.py tests/unit/db/test_session.py -q
uv run ruff check src/vyu/db tests/unit/db
uv run mypy
```

Expected: four tests pass and static checks exit `0`.

- [ ] **Step 6: Commit database configuration**

```powershell
git add src/vyu/db tests/unit/db pyproject.toml
git commit -m "feat: add PostgreSQL configuration and transaction boundary"
```

## Task 3: Create the Initial Alembic Schema

**Files:**

- Create: `alembic.ini`
- Create: `src/vyu/migrations/env.py`
- Create: `src/vyu/migrations/script.py.mako`
- Create: `src/vyu/migrations/versions/0001_tenancy_audit.py`
- Create: `src/vyu/db/models/__init__.py`
- Create: `src/vyu/db/models/base.py`
- Create: `src/vyu/db/models/tenancy.py`
- Create: `src/vyu/db/models/audit.py`
- Create: `tests/integration/db/test_migrations.py`

- [ ] **Step 1: Initialize Alembic and create model files**

Run once:

```powershell
uv run alembic init src/vyu/migrations
```

Replace generated configuration so `alembic.ini` contains:

```ini
[alembic]
script_location = src/vyu/migrations
prepend_sys_path = .

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

Create `src/vyu/db/models/base.py`:

```python
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, MetaData, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UuidPrimaryKeyMixin:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
```

Create `src/vyu/db/models/tenancy.py`:

```python
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.vyu.db.models.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class Tenant(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tenants"

    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")


class Workspace(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workspaces"
    __table_args__ = (UniqueConstraint("tenant_id", "slug"),)

    tenant_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")


class User(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    issuer: Mapped[str] = mapped_column(String(500), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    __table_args__ = (UniqueConstraint("issuer", "subject"),)


class Membership(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)

    tenant_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
```

Create `src/vyu/db/models/audit.py`:

```python
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Index, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from src.vyu.db.models.base import Base, UuidPrimaryKeyMixin


class AuditEvent(UuidPrimaryKeyMixin, Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_scope_time", "tenant_id", "workspace_id", "occurred_at"),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    trace_id: Mapped[str | None] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
```

Create `src/vyu/db/models/__init__.py`:

```python
from src.vyu.db.models.audit import AuditEvent
from src.vyu.db.models.base import Base
from src.vyu.db.models.tenancy import Membership, Tenant, User, Workspace

__all__ = ["AuditEvent", "Base", "Membership", "Tenant", "User", "Workspace"]
```

- [ ] **Step 2: Configure Alembic to read validated settings**

In generated `src/vyu/migrations/env.py`, import `Base` and `DatabaseSettings`, set `target_metadata = Base.metadata`, and set the URL without logging the password:

```python
from src.vyu.db.models import Base
from src.vyu.db.settings import DatabaseSettings

config.set_main_option("sqlalchemy.url", DatabaseSettings().database_url.replace("%", "%%"))
target_metadata = Base.metadata
```

Keep Alembic's generated online/offline migration functions. Do not print `sqlalchemy.url`.

- [ ] **Step 3: Generate and review migration `0001`**

```powershell
uv run alembic revision --autogenerate -m "create tenancy and audit tables" --rev-id 0001
```

Rename the generated file to `src/vyu/migrations/versions/0001_tenancy_audit.py`. Add to `upgrade()` after table creation:

```python
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    for table in ("workspaces", "memberships", "audit_events"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    op.execute(
        """
        CREATE POLICY workspaces_scope ON workspaces
        USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
        """
    )
    for table in ("memberships", "audit_events"):
        op.execute(
            f"""
            CREATE POLICY {table}_scope ON {table}
            USING (
                tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
                AND workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid
            )
            WITH CHECK (
                tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
                AND workspace_id = nullif(current_setting('app.workspace_id', true), '')::uuid
            )
            """
        )
```

Add matching `DROP POLICY` statements before table drops in `downgrade()`.

- [ ] **Step 4: Write migration integration tests**

Create `tests/integration/db/test_migrations.py` using a PostgreSQL testcontainer. The test must:

1. Set `VYU_DATABASE_URL` to the container URL converted to `postgresql+psycopg://`.
2. Run `alembic upgrade head`.
3. Assert current revision is `0001`.
4. Query `pg_extension` and assert `vector` exists.
5. Query `pg_policies` and assert policies exist for `workspaces`, `memberships`, and `audit_events`.
6. Run `alembic downgrade base` and assert the four tables are absent.
7. Run `alembic upgrade head` again to prove repeatability.

Use `subprocess.run(..., check=True, env=environment)` for Alembic and SQLAlchemy `inspect(engine).get_table_names()` for table assertions.

- [ ] **Step 5: Verify migrations**

```powershell
$env:VYU_DATABASE_URL='postgresql+psycopg://vyu_app:local-vyu-password@127.0.0.1:5432/vyu'
uv run alembic downgrade base
uv run alembic upgrade head
uv run alembic current
uv run pytest tests/integration/db/test_migrations.py -q
```

Expected: current revision `0001`; migration integration test passes.

- [ ] **Step 6: Commit schema foundation**

```powershell
git add alembic.ini src/vyu/db/models src/vyu/migrations tests/integration/db pyproject.toml
git commit -m "feat: add PostgreSQL tenancy and audit schema"
```

## Task 4: Prove Tenant Isolation with RLS

**Files:**

- Create: `tests/integration/db/test_tenant_rls.py`
- Modify: `src/vyu/migrations/versions/0001_tenancy_audit.py`

- [ ] **Step 1: Write a cross-tenant integration test**

The test creates two tenants, two workspaces, and one membership per workspace using a migration/administrative connection. With an application transaction:

```python
scope_a = TenantScope(tenant_id=tenant_a, workspace_id=workspace_a)
scope_b = TenantScope(tenant_id=tenant_b, workspace_id=workspace_b)

with transaction(factory, scope=scope_a) as session:
    visible = session.scalars(select(Membership)).all()
    assert [row.tenant_id for row in visible] == [tenant_a]

with transaction(factory, scope=scope_b) as session:
    visible = session.scalars(select(Membership)).all()
    assert [row.tenant_id for row in visible] == [tenant_b]
```

Also assert that an unscoped application transaction returns no memberships and that scope A cannot insert a row carrying tenant B/workspace B.

- [ ] **Step 2: Run and inspect the first failure**

```powershell
uv run pytest tests/integration/db/test_tenant_rls.py -q
```

Expected initial failure: rows remain visible because the local table owner bypasses RLS or the application and migration roles are not separated.

- [ ] **Step 3: Separate migration and application roles locally**

Update `compose.yaml` initialization to create:

- `vyu_migrator`, owner of schema objects.
- `vyu_app`, login role with CRUD privileges but not `BYPASSRLS`.

Mount a tracked `deploy/local/postgres/001_roles.sql` initialization script. Use local-only passwords `local-migrator-password` and `local-vyu-password`. Update `.env.example` with `VYU_MIGRATION_DATABASE_URL` and keep `VYU_DATABASE_URL` for the application role.

The script must revoke `CREATE` on schema `public` from `PUBLIC`, grant schema usage to `vyu_app`, and grant table/sequence privileges after migrations. Production Plan 4 reproduces these roles through RDS-compatible Terraform/bootstrap tasks without storing passwords in Terraform state.

- [ ] **Step 4: Recreate the local volume and rerun RLS tests**

This is destructive to local development data and must be run only after confirming the database contains fixtures, not required work:

```powershell
docker compose down
docker volume rm vyu_vyu-postgres-data
docker compose up -d postgres
uv run alembic upgrade head
uv run pytest tests/integration/db/test_tenant_rls.py -q
```

Expected: scope A sees only A, scope B sees only B, unscoped sees none, and cross-scope insert fails with an RLS violation.

- [ ] **Step 5: Commit enforced isolation**

```powershell
git add compose.yaml .env.example deploy/local/postgres/001_roles.sql src/vyu/migrations/versions/0001_tenancy_audit.py tests/integration/db/test_tenant_rls.py
git commit -m "security: enforce PostgreSQL tenant row isolation"
```

## Task 5: Add Focused Tenancy and Audit Repositories

**Files:**

- Create: `src/vyu/db/repositories/__init__.py`
- Create: `src/vyu/db/repositories/tenancy.py`
- Create: `src/vyu/db/repositories/audit.py`
- Create: `tests/integration/db/test_tenancy_repository.py`
- Create: `tests/integration/db/test_audit_repository.py`

- [ ] **Step 1: Write repository tests first**

Tenancy tests must prove:

- Tenant slug is unique.
- Workspace slug is unique within a tenant.
- `get_active_membership(user_id, scope)` returns only an active exact-scope membership.
- Suspended tenant, workspace, user, or membership returns no active membership.
- Cross-tenant reads return `None`.

Audit tests must prove:

- `append(event)` writes one row.
- Appending the same UUID twice raises a typed duplicate error and does not overwrite.
- `list_for_resource` is tenant/workspace scoped and time ordered.
- No update or delete method exists on `AuditRepository`.
- A database trigger rejects `UPDATE` and `DELETE` on `audit_events` for the application role.

- [ ] **Step 2: Implement typed records and repository methods**

Use dataclasses for inputs/outputs and accept an existing SQLAlchemy `Session`; repositories do not commit. Required signatures:

```python
class TenancyRepository:
    def __init__(self, session: Session) -> None: ...
    def add_tenant(self, record: NewTenant) -> TenantRecord: ...
    def add_workspace(self, record: NewWorkspace) -> WorkspaceRecord: ...
    def upsert_user(self, record: IdentityUser) -> UserRecord: ...
    def add_membership(self, record: NewMembership) -> MembershipRecord: ...
    def get_active_membership(
        self, *, user_id: UUID, scope: TenantScope
    ) -> MembershipRecord | None: ...

class AuditRepository:
    def __init__(self, session: Session) -> None: ...
    def append(self, event: NewAuditEvent) -> AuditEventRecord: ...
    def list_for_resource(
        self,
        *,
        scope: TenantScope,
        resource_type: str,
        resource_id: str,
        limit: int = 100,
    ) -> list[AuditEventRecord]: ...
```

Map SQLAlchemy `IntegrityError` to package-specific errors without returning database messages to API callers.

- [ ] **Step 3: Add append-only database enforcement**

Create migration `0002_audit_append_only.py` with a PostgreSQL trigger function that raises `audit_events are append-only` for `UPDATE` or `DELETE`, and attach it to `audit_events`. The downgrade drops the trigger and function.

- [ ] **Step 4: Run repository and migration tests**

```powershell
uv run alembic upgrade head
uv run pytest tests/integration/db/test_tenancy_repository.py tests/integration/db/test_audit_repository.py tests/integration/db/test_migrations.py -q
uv run ruff check src/vyu/db tests/integration/db
uv run mypy
```

Expected: repository, RLS, migration, lint, and type checks pass. Current Alembic revision is `0002`.

- [ ] **Step 5: Commit repositories**

```powershell
git add src/vyu/db/repositories src/vyu/migrations/versions/0002_audit_append_only.py tests/integration/db pyproject.toml
git commit -m "feat: add scoped tenancy and append-only audit repositories"
```

## Task 6: Import the Existing Tenant Registry Idempotently

**Files:**

- Create: `scripts/import_tenant_registry.py`
- Create: `tests/integration/db/test_import_tenant_registry.py`
- Modify: `docs/production/tenant-governance.md`

- [ ] **Step 1: Write import acceptance tests**

Use a temporary registry derived from `config/tenant_governance.local.example.json`. Prove:

- First run creates expected tenant, workspace, user, and membership records.
- Second run creates no duplicates and returns zero created counts.
- Invalid role/status aborts before writing.
- Existing record with conflicting immutable identity aborts and reports the safe record identifier.
- Import writes one audit event per created or changed governance record.

- [ ] **Step 2: Implement an explicit dry-run/import CLI**

Required command:

```powershell
uv run python scripts/import_tenant_registry.py --registry config/tenant_governance.local.example.json --dry-run
uv run python scripts/import_tenant_registry.py --registry config/tenant_governance.local.example.json --apply
```

The script must require exactly one of `--dry-run` or `--apply`, use `VYU_MIGRATION_DATABASE_URL` for administrative seeding, validate the entire JSON before opening a write transaction, and print counts without credentials or API-key hashes.

- [ ] **Step 3: Verify idempotency and safe output**

```powershell
uv run pytest tests/integration/db/test_import_tenant_registry.py -q
uv run python scripts/import_tenant_registry.py --registry config/tenant_governance.local.example.json --dry-run
```

Expected: tests pass and dry-run prints valid tenant/workspace/membership counts with no secret material.

- [ ] **Step 4: Document the one-time migration**

Update `docs/production/tenant-governance.md` with prerequisites, dry-run, backup, apply, verification query, rollback decision, and the statement that JSON is no longer authoritative after import.

- [ ] **Step 5: Commit the importer**

```powershell
git add scripts/import_tenant_registry.py tests/integration/db/test_import_tenant_registry.py docs/production/tenant-governance.md
git commit -m "feat: import tenant governance into PostgreSQL"
```

## Task 7: Add PostgreSQL CI and Exit Evidence

**Files:**

- Modify: `.github/workflows/ci.yml`
- Modify: `scripts/verify.py`
- Modify: `tests/test_verify_script.py`
- Modify: `docs/production/IMPLEMENTATION_STATUS.md`

- [ ] **Step 1: Add an integration verification scope**

Extend `Scope` with `integration`, add command:

```python
Command(
    "postgres-integration",
    ("uv", "run", "pytest", "tests/integration/db", "-q"),
)
```

Update tests to assert the new scope contains only database integration tests.

- [ ] **Step 2: Add PostgreSQL to backend CI**

Add a `postgres:17` service with health checks to the backend job, set test-only `VYU_DATABASE_URL` and `VYU_MIGRATION_DATABASE_URL`, run `uv run alembic upgrade head`, then run integration scope. Use a separate application and migration role initialization step matching local role separation.

- [ ] **Step 3: Verify CI from a clean pull request**

Expected checks:

- Frozen dependency sync passes.
- Alembic upgrades an empty database to `0002`.
- Unit, migration, repository, importer, and RLS tests pass.
- No SQLite path is used by new production database tests.

- [ ] **Step 4: Update status evidence**

Mark Plan 2 `complete` only after CI and a local clean database run pass. Record migration revision `0002`, CI URL, merge SHA, and the RLS test evidence.

- [ ] **Step 5: Commit Plan 2 evidence**

```powershell
git add .github/workflows/ci.yml scripts/verify.py tests/test_verify_script.py docs/production/IMPLEMENTATION_STATUS.md
git commit -m "ci: verify PostgreSQL migrations and tenant isolation"
```

## Exit Gate

Plan 2 is complete only when:

- PostgreSQL 17 plus pgvector starts locally from pinned configuration.
- Alembic upgrades an empty database to revision `0002`, downgrades, and upgrades again.
- Application startup code performs no DDL.
- Migration and application roles are separate.
- RLS tests prove cross-tenant reads and writes are blocked.
- Focused tenancy and append-only audit repositories pass integration tests.
- Existing JSON governance imports idempotently and becomes non-authoritative.
- Database settings reject SQLite for the production path.
- CI runs PostgreSQL migrations and integration tests from a clean environment.
- The original SQLite test suite still passes during transition.

## Handoff to Plan 3

Plan 3 uses `DatabaseSettings`, `transaction`, `TenantScope`, `TenancyRepository`, and `AuditRepository`. It adds job/outbox/research tables through revision `0003`; it must not bypass tenant-scoped transactions or publish SQS messages before the database transaction commits.

