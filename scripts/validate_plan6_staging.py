from __future__ import annotations

"""Operator checklist for Plan 6 staging validation.

This script documents the required staging evidence collection steps. It does not
call live providers unless the environment explicitly enables them.
"""

import argparse
import json
from pathlib import Path


CHECKLIST = [
    "Run live PubMed probe with VYU_RUN_LIVE_PUBMED_PROBE=1",
    "Execute a research.run job against approved PubMed policy",
    "Build the same retrieval index twice and confirm manifest checksum reuse",
    "Force PubMed timeout/429 and confirm bounded retry visibility",
    "Attempt cross-tenant evidence/index access and confirm denial",
    "Exercise index build failure and confirm previous active index remains",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan 6 staging validation checklist.")
    parser.add_argument(
        "--output",
        default="evidence/plan6-staging-validation.json",
        help="Path for the staging evidence template.",
    )
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "plan": 6,
        "status": "operator_pending",
        "checklist": CHECKLIST,
        "notes": "Populate with staging command output and benchmark report links.",
    }
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote staging validation template to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
