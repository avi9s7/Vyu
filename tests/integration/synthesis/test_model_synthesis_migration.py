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


def test_model_synthesis_migration_upgrade_downgrade_and_repeat(postgres_urls: dict[str, str]) -> None:
    migration_url = postgres_urls["migration"]
    subprocess.run(
        ["uv", "run", "alembic", "downgrade", "0008"],
        cwd=ROOT,
        check=True,
        env=_alembic_env(migration_url),
    )
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "0009"],
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
                        'model_policy_versions',
                        'prompt_templates',
                        'model_calls',
                        'answers',
                        'answer_claims',
                        'claim_citations'
                      )
                    """
                )
            )
        }
        policies = {
            row[0]
            for row in connection.execute(
                text(
                    """
                    SELECT tablename
                    FROM pg_policies
                    WHERE tablename IN (
                        'model_calls',
                        'answers',
                        'answer_claims',
                        'claim_citations'
                    )
                    """
                )
            )
        }
    assert tables == {
        "model_policy_versions",
        "prompt_templates",
        "model_calls",
        "answers",
        "answer_claims",
        "claim_citations",
    }
    assert policies == {"model_calls", "answers", "answer_claims", "claim_citations"}
    subprocess.run(
        ["uv", "run", "alembic", "downgrade", "0008"],
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
