#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from src.vyu.db.session import build_engine, build_session_factory
from src.vyu.db.settings import DatabaseSettings
from src.vyu.policy.repository import PolicyRepository, canonical_policy_hash
from src.vyu.research_mcp.registry import ResearchToolRegistry
from src.vyu.sources import SourceRegistry


@dataclass(frozen=True)
class ImportPolicyCounts:
    sources: int
    tools: int
    approved_sources: int
    approved_tools: int
    source_policy_hash: str
    tool_policy_hash: str


def load_policy_payloads(
    *,
    source_registry_path: Path,
    tool_registry_path: Path,
) -> tuple[SourceRegistry, ResearchToolRegistry]:
    source_registry = SourceRegistry.read(source_registry_path)
    tool_registry = ResearchToolRegistry.read(tool_registry_path)
    return source_registry, tool_registry


def preview_import(
    *,
    source_registry_path: Path,
    tool_registry_path: Path,
) -> ImportPolicyCounts:
    source_registry, tool_registry = load_policy_payloads(
        source_registry_path=source_registry_path,
        tool_registry_path=tool_registry_path,
    )
    sources = [source_registry.get(source_id) for source_id in source_registry.source_ids()]
    tools = [tool_registry.get(tool_id) for tool_id in tool_registry.tool_ids()]
    source_payload = {"sources": [source.to_json() for source in sources]}
    tool_payload = {"tools": [tool.to_json() for tool in tools]}
    return ImportPolicyCounts(
        sources=len(sources),
        tools=len(tools),
        approved_sources=sum(1 for source in sources if source.approved),
        approved_tools=sum(1 for tool in tools if tool.approved),
        source_policy_hash=canonical_policy_hash(source_payload),
        tool_policy_hash=canonical_policy_hash(tool_payload),
    )


def import_policies(
    *,
    source_registry_path: Path,
    tool_registry_path: Path,
    actor_id: str,
    apply: bool,
) -> ImportPolicyCounts:
    source_registry, tool_registry = load_policy_payloads(
        source_registry_path=source_registry_path,
        tool_registry_path=tool_registry_path,
    )
    sources = [source_registry.get(source_id) for source_id in source_registry.source_ids()]
    tools = [tool_registry.get(tool_id) for tool_id in tool_registry.tool_ids()]
    preview = preview_import(
        source_registry_path=source_registry_path,
        tool_registry_path=tool_registry_path,
    )
    if not apply:
        return preview

    settings = DatabaseSettings()
    factory = build_session_factory(
        build_engine(
            DatabaseSettings(
                database_url=settings.migration_database_url,
                migration_database_url=settings.migration_database_url,
            )
        )
    )
    repository = PolicyRepository()
    with factory.begin() as session:
        repository.activate_policies(
            session,
            sources=sources,
            tools=tools,
            actor_id=actor_id,
        )
    return preview


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import versioned source and research tool policy.")
    parser.add_argument(
        "--source-registry",
        default="config/source_registry.example.json",
        type=Path,
    )
    parser.add_argument(
        "--tool-registry",
        default="config/research_tool_registry.example.json",
        type=Path,
    )
    parser.add_argument("--actor", default="import_source_policy")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    counts = import_policies(
        source_registry_path=args.source_registry,
        tool_registry_path=args.tool_registry,
        actor_id=args.actor,
        apply=args.apply,
    )
    print(json.dumps(asdict(counts), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
