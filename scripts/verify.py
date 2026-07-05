from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Literal, Sequence


Scope = Literal["backend", "frontend", "integration", "all"]


@dataclass(frozen=True)
class Command:
    name: str
    argv: tuple[str, ...]


def default_npm_executable() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def commands_for_scope(scope: Scope, *, npm: str) -> list[Command]:
    backend = [
        Command("ruff", ("uv", "run", "ruff", "check", "src", "apps/serverless", "scripts", "tests")),
        Command("mypy", ("uv", "run", "mypy", "--follow-imports=skip")),
        Command("python-tests", ("uv", "run", "python", "-m", "unittest", "discover")),
    ]
    integration = [
        Command(
            "postgres-integration",
            ("uv", "run", "pytest", "tests/integration/db", "-q"),
        ),
    ]
    frontend = [
        Command("npm-ci", (npm, "ci", "--prefix", "apps/web")),
        Command("frontend-typecheck", (npm, "run", "typecheck", "--prefix", "apps/web")),
        Command("frontend-lint", (npm, "run", "lint", "--prefix", "apps/web")),
        Command("frontend-tests", (npm, "test", "--prefix", "apps/web")),
        Command("frontend-build", (npm, "run", "build", "--prefix", "apps/web")),
    ]
    if scope == "backend":
        return backend
    if scope == "integration":
        return integration
    if scope == "frontend":
        return frontend
    return [*backend, *integration, *frontend]


def run_commands(commands: Sequence[Command]) -> int:
    for command in commands:
        print(f"==> {command.name}: {' '.join(command.argv)}", flush=True)
        completed = subprocess.run(command.argv, check=False)
        if completed.returncode != 0:
            print(f"FAILED: {command.name} exited {completed.returncode}", file=sys.stderr)
            return completed.returncode
    print("Verification passed.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the VYU repository.")
    parser.add_argument(
        "--scope",
        choices=("backend", "frontend", "integration", "all"),
        default="all",
    )
    args = parser.parse_args(argv)
    return run_commands(
        commands_for_scope(args.scope, npm=default_npm_executable())
    )


if __name__ == "__main__":
    raise SystemExit(main())
