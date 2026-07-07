from __future__ import annotations

import os
import subprocess
from pathlib import Path

import psycopg
from sqlalchemy import create_engine, inspect

ROOT = Path(__file__).resolve().parents[3]

INGESTION_TABLES = (
    "documents",
    "document_versions",
    "evidence_objects",
    "document_chunks",
    "ingestion_events",
)


def _alembic_env(migration_url: str) -> dict[str, str]:
    return {
        **os.environ,
        "VYU_MIGRATION_DATABASE_URL": migration_url,
        "VYU_DATABASE_URL": migration_url,
    }


def test_ingestion_migration_upgrade_downgrade_and_repeat(postgres_urls: dict[str, str]) -> None:
    migration_url = postgres_urls["migration"]
    psycopg_url = migration_url.replace("postgresql+psycopg://", "postgresql://")

    subprocess.run(
        ["uv", "run", "alembic", "downgrade", "0003"],
        cwd=ROOT,
        check=True,
        env=_alembic_env(migration_url),
    )
    engine = create_engine(migration_url)
    assert "documents" not in inspect(engine).get_table_names()

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
    assert set(INGESTION_TABLES).issubset(table_names)

    with psycopg.connect(psycopg_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tablename FROM pg_policies WHERE tablename = ANY(%s)",
                (list(INGESTION_TABLES),),
            )
            policies = {row[0] for row in cursor.fetchall()}
            assert policies == set(INGESTION_TABLES)

            cursor.execute(
                """
                SELECT indexname FROM pg_indexes
                WHERE indexname IN (
                    'documents_external_id_unique',
                    'document_versions_document_version_unique',
                    'document_chunks_version_ordinal_unique',
                    'document_chunks_version_citation_unique',
                    'ingestion_events_job_sequence_unique'
                )
                """
            )
            indexes = {row[0] for row in cursor.fetchall()}
            assert indexes == {
                "documents_external_id_unique",
                "document_versions_document_version_unique",
                "document_chunks_version_ordinal_unique",
                "document_chunks_version_citation_unique",
                "ingestion_events_job_sequence_unique",
            }

            cursor.execute(
                """
                SELECT conname FROM pg_constraint
                WHERE conname IN (
                    'ck_documents_documents_status_valid',
                    'ck_document_versions_document_versions_malware_status_valid',
                    'ck_document_versions_document_versions_phi_status_valid'
                )
                """
            )
            constraints = {row[0] for row in cursor.fetchall()}
            assert constraints == {
                "ck_documents_documents_status_valid",
                "ck_document_versions_document_versions_malware_status_valid",
                "ck_document_versions_document_versions_phi_status_valid",
            }

    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=ROOT,
        check=True,
        env=_alembic_env(migration_url),
    )
