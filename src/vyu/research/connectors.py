from __future__ import annotations

import os
from pathlib import Path

from src.vyu.config import RuntimeSettings
from src.vyu.connectors import SourceConnector
from src.vyu.connectors.pubmed import ProductionPubMedConnector
from src.vyu.connectors.pubmed_live import PubMedHttpTransport, PubMedReplayTransport


def connector_mode() -> str:
    return os.environ.get("VYU_RESEARCH_CONNECTOR_MODE", "replay").strip().lower()


def build_research_connectors(
    *,
    source_ids: set[str],
    runtime_settings: RuntimeSettings | None = None,
) -> dict[str, SourceConnector]:
    settings = runtime_settings or RuntimeSettings.from_environment()
    connectors: dict[str, SourceConnector] = {}
    if "pubmed" in source_ids:
        if connector_mode() == "live":
            connectors["pubmed"] = ProductionPubMedConnector(
                transport=PubMedHttpTransport(
                    tool=settings.ncbi_tool,
                    email=settings.ncbi_email,
                    api_key=settings.ncbi_api_key,
                    timeout_seconds=settings.connector_timeout_seconds,
                )
            )
        else:
            fixture_path = Path(
                os.environ.get(
                    "VYU_RESEARCH_PUBMED_FIXTURE",
                    "tests/fixtures/connectors/pubmed/replay.json",
                )
            )
            connectors["pubmed"] = ProductionPubMedConnector(
                transport=PubMedReplayTransport(fixture_path)
            )
    return connectors
