from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from testcontainers.postgres import PostgresContainer

ROOT = Path(__file__).resolve().parents[3]
ROLES_SQL = ROOT / "deploy" / "local" / "postgres" / "001_roles.sql"


def _psycopg_url(container: PostgresContainer) -> str:
    return (
        f"postgresql://{container.username}:{container.password}"
        f"@{container.get_container_host_ip()}:{container.get_exposed_port(5432)}"
        f"/{container.dbname}"
    )


def _sqlalchemy_psycopg_url(container: PostgresContainer, user: str, password: str) -> str:
    return (
        f"postgresql+psycopg://{user}:{password}"
        f"@{container.get_container_host_ip()}:{container.get_exposed_port(5432)}"
        f"/{container.dbname}"
    )


def _bootstrap_roles_psycopg_url(psycopg_url: str, dbname: str) -> None:
    with psycopg.connect(psycopg_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s", ("vyu_migrator",)
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    "CREATE ROLE vyu_migrator WITH LOGIN PASSWORD %s",
                    ("local-migrator-password",),
                )
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", ("vyu_app",))
            if cursor.fetchone() is None:
                cursor.execute(
                    "CREATE ROLE vyu_app WITH LOGIN PASSWORD %s",
                    ("local-vyu-password",),
                )
            cursor.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            cursor.execute(f"GRANT ALL PRIVILEGES ON DATABASE {dbname} TO vyu_migrator")
            cursor.execute(f"ALTER DATABASE {dbname} OWNER TO vyu_migrator")
            cursor.execute("GRANT CREATE ON SCHEMA public TO vyu_migrator")
            cursor.execute("GRANT USAGE ON SCHEMA public TO vyu_app")
            cursor.execute("ALTER ROLE vyu_app NOBYPASSRLS NOSUPERUSER")
            cursor.execute("ALTER ROLE vyu_migrator NOBYPASSRLS")
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")


def _bootstrap_roles(container: PostgresContainer) -> None:
    _bootstrap_roles_psycopg_url(_psycopg_url(container), container.dbname)


def _run_alembic(database_url: str, *args: str) -> None:
    environment = os.environ.copy()
    environment["VYU_MIGRATION_DATABASE_URL"] = database_url
    environment["VYU_DATABASE_URL"] = database_url
    subprocess.run(
        ["uv", "run", "alembic", *args],
        cwd=ROOT,
        check=True,
        env=environment,
    )


@pytest.fixture(scope="session")
def postgres_urls() -> Iterator[dict[str, str]]:
    migration_url = os.environ.get("VYU_MIGRATION_DATABASE_URL")
    app_url = os.environ.get("VYU_DATABASE_URL")
    if migration_url and app_url:
        admin_url = os.environ.get("VYU_ADMIN_DATABASE_URL", migration_url)
        admin_psycopg = admin_url.replace("postgresql+psycopg://", "postgresql://")
        dbname = admin_psycopg.rsplit("/", 1)[-1]
        _bootstrap_roles_psycopg_url(admin_psycopg, dbname)
        _run_alembic(migration_url, "upgrade", "head")
        yield {
            "migration": migration_url,
            "app": app_url,
            "admin": migration_url,
        }
        return

    with PostgresContainer("pgvector/pgvector:0.8.0-pg17") as container:
        _bootstrap_roles(container)
        migration_url = _sqlalchemy_psycopg_url(
            container, "vyu_migrator", "local-migrator-password"
        )
        app_url = _sqlalchemy_psycopg_url(container, "vyu_app", "local-vyu-password")
        _run_alembic(migration_url, "upgrade", "head")
        yield {
            "migration": migration_url,
            "app": app_url,
            "admin": migration_url,
        }
