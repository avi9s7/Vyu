from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vyu.deployment import (  # noqa: E402
    DeploymentOperatorConfigError,
    load_deployment_operator_env,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Vyu local deployment config file.")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument(
        "--allow-placeholder-secret",
        action="store_true",
        help="Allow template placeholder secrets while validating the checked-in example file.",
    )
    args = parser.parse_args()

    try:
        config = load_deployment_operator_env(
            args.env_file,
            allow_placeholder_secret=args.allow_placeholder_secret,
        )
    except DeploymentOperatorConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    payload = {
        "status": "valid",
        "env_file": str(args.env_file),
        "config": config.safe_summary(),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
