from __future__ import annotations

import os
import subprocess
from pathlib import Path

import psycopg
from sqlalchemy import create_engine, inspect

ROOT = Path(__file__).resolve().parents[3]

JOB_TABLES = (
    "jobs",
    "idempotency_keys",
    "outbox_events",
    "research_runs",
    "research_run_events",
)


def _alembic_env(migration_url: str) -> dict[str, str]:
    return {
        **os.environ,
        "VYU_MIGRATION_DATABASE_URL": migration_url,
        "VYU_DATABASE_URL": migration_url,
    }


def test_job_migration_upgrade_downgrade_and_repeat(postgres_urls: dict[str, str]) -> None:
    migration_url = postgres_urls["migration"]
    psycopg_url = migration_url.replace("postgresql+psycopg://", "postgresql://")

    subprocess.run(
        ["uv", "run", "alembic", "downgrade", "0002"],
        cwd=ROOT,
        check=True,
        env=_alembic_env(migration_url),
    )
    engine = create_engine(migration_url)
    assert "jobs" not in inspect(engine).get_table_names()

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
    assert "0004" in current.stdout

    table_names = set(inspect(engine).get_table_names())
    assert set(JOB_TABLES).issubset(table_names)

    with psycopg.connect(psycopg_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tablename FROM pg_policies WHERE tablename = ANY(%s)",
                (list(JOB_TABLES),),
            )
            policies = {row[0] for row in cursor.fetchall()}
            assert policies == set(JOB_TABLES)

            cursor.execute(
                """
                SELECT conname FROM pg_constraint
                WHERE conname IN (
                    'ck_jobs_jobs_status_valid',
                    'ck_research_runs_research_runs_status_valid'
                )
                """
            )
            constraints = {row[0] for row in cursor.fetchall()}
            assert constraints == {
                "ck_jobs_jobs_status_valid",
                "ck_research_runs_research_runs_status_valid",
            }

            cursor.execute(
                """
                SELECT indexname FROM pg_indexes
                WHERE indexname IN ('ix_jobs_lease', 'ix_outbox_events_unpublished')
                """
            )
            indexes = {row[0] for row in cursor.fetchall()}
            assert indexes == {"ix_jobs_lease", "ix_outbox_events_unpublished"}

    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=ROOT,
        check=True,
        env=_alembic_env(migration_url),
    )
