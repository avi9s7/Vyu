from __future__ import annotations

import subprocess
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]


def _alembic_env(migration_url: str) -> dict[str, str]:
    import os

    return {
        **os.environ,
        "VYU_MIGRATION_DATABASE_URL": migration_url,
        "VYU_DATABASE_URL": migration_url,
    }


def test_retrieval_migration_upgrade_downgrade_and_repeat(postgres_urls: dict[str, str]) -> None:
    migration_url = postgres_urls["migration"]
    subprocess.run(
        ["uv", "run", "alembic", "downgrade", "0007"],
        cwd=ROOT,
        check=True,
        env=_alembic_env(migration_url),
    )
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "0008"],
        cwd=ROOT,
        check=True,
        env=_alembic_env(migration_url),
    )
    engine = create_engine(migration_url)
    with engine.connect() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name IN (
                        'retrieval_indexes',
                        'chunk_embeddings',
                        'retrieval_runs',
                        'retrieval_hits',
                        'retrieval_exclusions'
                      )
                    """
                )
            )
        }
        vector_type = connection.execute(
            text(
                """
                SELECT format_type(a.atttypid, a.atttypmod)
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid
                WHERE c.relname = 'chunk_embeddings'
                  AND a.attname = 'embedding'
                """
            )
        ).scalar_one()
        policies = {
            row[0]
            for row in connection.execute(
                text(
                    """
                    SELECT tablename
                    FROM pg_policies
                    WHERE tablename IN (
                        'retrieval_indexes',
                        'chunk_embeddings',
                        'retrieval_runs',
                        'retrieval_hits',
                        'retrieval_exclusions'
                    )
                    """
                )
            )
        }
    assert tables == {
        "retrieval_indexes",
        "chunk_embeddings",
        "retrieval_runs",
        "retrieval_hits",
        "retrieval_exclusions",
    }
    assert vector_type == "vector(1536)"
    assert policies == {
        "retrieval_indexes",
        "chunk_embeddings",
        "retrieval_runs",
        "retrieval_hits",
        "retrieval_exclusions",
    }
    subprocess.run(
        ["uv", "run", "alembic", "downgrade", "0007"],
        cwd=ROOT,
        check=True,
        env=_alembic_env(migration_url),
    )
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=ROOT,
        check=True,
        env=_alembic_env(migration_url),
    )
