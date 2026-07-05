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


def _bootstrap_roles(container: PostgresContainer) -> None:
    dbname = container.dbname
    with psycopg.connect(_psycopg_url(container), autocommit=True) as connection:
        connection.execute(
            f"""
            CREATE ROLE vyu_migrator WITH LOGIN PASSWORD 'local-migrator-password';
            CREATE ROLE vyu_app WITH LOGIN PASSWORD 'local-vyu-password';
            REVOKE CREATE ON SCHEMA public FROM PUBLIC;
            GRANT ALL PRIVILEGES ON DATABASE {dbname} TO vyu_migrator;
            GRANT CREATE ON SCHEMA public TO vyu_migrator;
            GRANT USAGE ON SCHEMA public TO vyu_app;
            ALTER ROLE vyu_app NOBYPASSRLS NOSUPERUSER;
            ALTER ROLE vyu_migrator NOBYPASSRLS;
            """
        )


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
    with PostgresContainer("pgvector/pgvector:0.8.0-pg17") as container:
        _bootstrap_roles(container)
        migration_url = _sqlalchemy_psycopg_url(
            container, "vyu_migrator", "local-migrator-password"
        )
        app_url = _sqlalchemy_psycopg_url(container, "vyu_app", "local-vyu-password")
        admin_url = _sqlalchemy_psycopg_url(
            container, container.username, container.password
        )
        _run_alembic(migration_url, "upgrade", "head")
        yield {
            "migration": migration_url,
            "app": app_url,
            "admin": admin_url,
        }
