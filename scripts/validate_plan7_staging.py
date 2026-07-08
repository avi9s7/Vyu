from __future__ import annotations

"""Operator checklist for Plan 7 staging validation.

This script documents the required staging evidence collection steps. It does not
call live providers unless the environment explicitly enables them.
"""

import argparse
import json
from pathlib import Path

from src.vyu.synthesis.staging_fixtures import (
    OPERATIONAL_FAILURE_SCENARIOS,
    PLAN7_STAGING_CHECKLIST,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan 7 staging validation checklist.")
    parser.add_argument(
        "--output",
        default="evidence/plan7-staging-validation.json",
        help="Path for the staging evidence template.",
    )
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "plan": 7,
        "status": "operator_pending",
        "checklist": list(PLAN7_STAGING_CHECKLIST),
        "operational_failure_scenarios": list(OPERATIONAL_FAILURE_SCENARIOS),
        "notes": (
            "Populate with staging command output, synthesis evaluation report, "
            "adjudication summary, alarm evidence, and promotion binding."
        ),
    }
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote staging validation template to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
