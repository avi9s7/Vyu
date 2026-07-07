#!/usr/bin/env python3
"""Generate a TypeScript declaration file from the exported OpenAPI schema."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def generate_typescript_client(
    *,
    openapi_path: Path,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if npx is None:
        raise RuntimeError("npx is required to generate the TypeScript API client.")
    command = [
        npx,
        "--yes",
        "openapi-typescript",
        str(openapi_path),
        "-o",
        str(output_path),
    ]
    subprocess.run(command, check=True, shell=sys.platform == "win32")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate VYU API TypeScript types.")
    parser.add_argument(
        "--openapi",
        default="docs/api/openapi.json",
        type=Path,
    )
    parser.add_argument(
        "--output",
        default="apps/web/src/lib/api/schema.d.ts",
        type=Path,
    )
    args = parser.parse_args()
    generate_typescript_client(openapi_path=args.openapi, output_path=args.output)


if __name__ == "__main__":
    main()
