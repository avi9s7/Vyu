from __future__ import annotations

from sqlalchemy import create_engine, text

from src.vyu.connectors.rate_limit import PostgresRateLimiter, StaticRateLimiter
from src.vyu.db.session import build_engine, build_session_factory
from src.vyu.db.settings import DatabaseSettings


def test_migration_creates_connector_rate_windows(postgres_urls: dict[str, str]) -> None:
    engine = create_engine(postgres_urls["migration"])
    with engine.connect() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = 'connector_rate_windows'
                    """
                )
            )
        }
    assert tables == {"connector_rate_windows"}


def test_postgres_rate_limiter_enforces_per_source_window(postgres_urls: dict[str, str]) -> None:
    settings = DatabaseSettings(database_url=postgres_urls["migration"])
    factory = build_session_factory(build_engine(settings))
    limiter = PostgresRateLimiter(
        factory,
        max_calls=1,
        window_seconds=60,
        clock=lambda: 1_700_000_000.0,
    )
    assert limiter.allow("pubmed") is True
    assert limiter.allow("pubmed") is False
    assert limiter.allow("clinicaltrials") is True


def test_static_rate_limiter_is_process_local() -> None:
    limiter = StaticRateLimiter(max_calls=2, window_seconds=60)
    assert limiter.allow("pubmed") is True
    assert limiter.allow("pubmed") is True
    assert limiter.allow("pubmed") is False
