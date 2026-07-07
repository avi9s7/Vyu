#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from src.vyu.connectors.health import ValidationStage
from src.vyu.connectors.pubmed.probe import PubMedStagingProbe, build_probe_connector


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the governed PubMed staging probe against replay or live transport.",
    )
    parser.add_argument(
        "--stage",
        choices=("replay", "live"),
        default="replay",
        help="Replay is the default offline-safe probe stage.",
    )
    parser.add_argument(
        "--fixture-path",
        type=Path,
        default=Path("tests/fixtures/connectors/pubmed/replay.json"),
        help="Replay fixture used when --stage replay.",
    )
    parser.add_argument("--query", default="aspirin")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write JSON probe evidence.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    stage = ValidationStage.REPLAY if args.stage == "replay" else ValidationStage.LIVE
    if stage == ValidationStage.LIVE and os.environ.get("VYU_RUN_LIVE_PUBMED_PROBE") != "1":
        print(
            "Live PubMed probe is gated. Set VYU_RUN_LIVE_PUBMED_PROBE=1 and NCBI contact settings.",
            file=sys.stderr,
        )
        return 2
    connector = build_probe_connector(stage=stage, fixture_path=args.fixture_path)
    result = PubMedStagingProbe(connector).run(
        stage=stage,
        query=args.query,
        limit=args.limit,
    )
    payload = result.to_json()
    print(json.dumps(payload, indent=2, sort_keys=True))
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if result.status.value == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
