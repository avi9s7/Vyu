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
