from __future__ import annotations

import subprocess
from sqlalchemy import create_engine, text

from src.vyu.policy.repository import canonical_policy_hash


def _alembic_env(migration_url: str) -> dict[str, str]:
    return {
        "VYU_MIGRATION_DATABASE_URL": migration_url,
        "VYU_DATABASE_URL": migration_url,
    }


def test_policy_migration_upgrade_downgrade_and_repeat(postgres_urls: dict[str, str]) -> None:
    migration_url = postgres_urls["migration"]
    subprocess.run(
        ["alembic", "downgrade", "0004"],
        cwd="src/vyu",
        env=_alembic_env(migration_url),
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["alembic", "upgrade", "0005"],
        cwd="src/vyu",
        env=_alembic_env(migration_url),
        check=True,
        capture_output=True,
        text=True,
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
                        'source_policy_versions',
                        'sources',
                        'research_tool_policy_versions',
                        'research_tools'
                      )
                    """
                )
            )
        }
    assert tables == {
        "source_policy_versions",
        "sources",
        "research_tool_policy_versions",
        "research_tools",
    }
    subprocess.run(
        ["alembic", "downgrade", "0004"],
        cwd="src/vyu",
        env=_alembic_env(migration_url),
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd="src/vyu",
        env=_alembic_env(migration_url),
        check=True,
        capture_output=True,
        text=True,
    )


def test_canonical_policy_hash_is_stable() -> None:
    payload = {"sources": [{"source_id": "pubmed", "approval_status": "approved"}]}
    assert canonical_policy_hash(payload) == canonical_policy_hash(payload)
