from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vyu.deployment import (  # noqa: E402
    DeploymentCommandTranscriptError,
    build_deployment_command_transcript,
    command_from_json,
    write_deployment_command_transcript,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write deterministic local transcript evidence from explicit deployment command-result metadata."
    )
    parser.add_argument(
        "--command-json",
        required=True,
        help='Command as a JSON array, for example: ["python", "scripts/validate_deployment_package.py"].',
    )
    parser.add_argument("--purpose", required=True, help="Human-readable command purpose.")
    parser.add_argument("--exit-code", type=int, required=True, help="Observed command exit code.")
    parser.add_argument("--started-at", required=True, help="Explicit command start timestamp.")
    parser.add_argument("--finished-at", required=True, help="Explicit command finish timestamp.")
    parser.add_argument("--stdout-text", default="", help="Captured stdout text. Do not include secrets.")
    parser.add_argument("--stderr-text", default="", help="Captured stderr text. Do not include secrets.")
    parser.add_argument("--stdout-file", type=Path, help="Path to a pre-captured stdout text file.")
    parser.add_argument("--stderr-file", type=Path, help="Path to a pre-captured stderr text file.")
    parser.add_argument(
        "--artifact",
        action="append",
        type=Path,
        default=[],
        help="Artifact path to summarize. May be provided more than once.",
    )
    parser.add_argument("--root", type=Path, default=Path("."), help="Repository root for artifact paths.")
    parser.add_argument("--output", type=Path, required=True, help="Output transcript JSON path.")
    parser.add_argument(
        "--excerpt-limit",
        type=int,
        default=240,
        help="Maximum stdout/stderr excerpt characters to store.",
    )
    args = parser.parse_args()

    try:
        if args.stdout_file is not None and args.stdout_text:
            raise DeploymentCommandTranscriptError("Use either --stdout-text or --stdout-file, not both.")
        if args.stderr_file is not None and args.stderr_text:
            raise DeploymentCommandTranscriptError("Use either --stderr-text or --stderr-file, not both.")
        stdout_text = _read_optional_text(args.stdout_file) if args.stdout_file is not None else args.stdout_text
        stderr_text = _read_optional_text(args.stderr_file) if args.stderr_file is not None else args.stderr_text
        transcript = build_deployment_command_transcript(
            command=command_from_json(args.command_json),
            purpose=args.purpose,
            exit_code=args.exit_code,
            started_at=args.started_at,
            finished_at=args.finished_at,
            stdout_text=stdout_text,
            stderr_text=stderr_text,
            artifact_paths=args.artifact,
            root=args.root,
            output_excerpt_limit=args.excerpt_limit,
        )
        write_deployment_command_transcript(transcript, args.output)
    except (DeploymentCommandTranscriptError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(transcript.to_json(), indent=2, sort_keys=True))
    return 0 if transcript.status == "passed" else 1


def _read_optional_text(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
