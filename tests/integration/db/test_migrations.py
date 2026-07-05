from __future__ import annotations

import os
import subprocess
from pathlib import Path

import psycopg
from sqlalchemy import create_engine, inspect

ROOT = Path(__file__).resolve().parents[3]


def _alembic_env(migration_url: str) -> dict[str, str]:
    return {
        **os.environ,
        "VYU_MIGRATION_DATABASE_URL": migration_url,
        "VYU_DATABASE_URL": migration_url,
    }


def test_migrations_upgrade_downgrade_and_repeat(postgres_urls: dict[str, str]) -> None:
    migration_url = postgres_urls["migration"]
    psycopg_url = migration_url.replace("postgresql+psycopg://", "postgresql://")

    subprocess.run(
        ["uv", "run", "alembic", "downgrade", "base"],
        cwd=ROOT,
        check=True,
        env=_alembic_env(migration_url),
    )
    engine = create_engine(migration_url)
    assert "tenants" not in inspect(engine).get_table_names()

    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=ROOT,
        check=True,
        env=_alembic_env(migration_url),
    )
    current = subprocess.run(
        ["uv", "run", "alembic", "current"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        env=_alembic_env(migration_url),
    )
    assert "0002" in current.stdout

    with psycopg.connect(psycopg_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            assert cursor.fetchone() is not None
            cursor.execute(
                "SELECT tablename FROM pg_policies WHERE tablename IN "
                "('workspaces', 'memberships', 'audit_events')"
            )
            policies = {row[0] for row in cursor.fetchall()}
            assert policies == {"workspaces", "memberships", "audit_events"}

    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=ROOT,
        check=True,
        env=_alembic_env(migration_url),
    )
