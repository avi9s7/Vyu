from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vyu.deployment import (  # noqa: E402
    DeploymentTranscriptBundleError,
    build_deployment_transcript_bundle,
    write_deployment_transcript_bundle,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check a local deployment command-transcript bundle without executing commands."
    )
    parser.add_argument("--manifest", type=Path, required=True, help="Deployment package manifest path.")
    parser.add_argument(
        "--transcript",
        action="append",
        type=Path,
        required=True,
        help="Command transcript JSON path. Provide once per transcript, in expected command order.",
    )
    parser.add_argument("--root", type=Path, default=Path("."), help="Repository root for transcript paths.")
    parser.add_argument("--created-at", help="Explicit bundle timestamp for deterministic output.")
    parser.add_argument("--output", type=Path, required=True, help="Output transcript bundle JSON path.")
    args = parser.parse_args()

    try:
        bundle = build_deployment_transcript_bundle(
            args.manifest,
            transcript_paths=args.transcript,
            root=args.root,
            created_at=args.created_at,
        )
        write_deployment_transcript_bundle(bundle, args.output)
    except (DeploymentTranscriptBundleError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(bundle.to_json(), indent=2, sort_keys=True))
    return 0 if bundle.status == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
