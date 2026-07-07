from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import create_engine

from src.vyu.api.app import create_app
from src.vyu.api.settings import ApiSettings


def export_openapi(output: Path) -> dict[str, object]:
    app = create_app(
        settings_override=ApiSettings(env="local", expected_migration_revision="0004"),
        engine_override=create_engine("sqlite+pysqlite:///:memory:"),
        schema_revision_override="0003",
    )
    schema = app.openapi()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return schema


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the VYU FastAPI OpenAPI schema.")
    parser.add_argument(
        "--output",
        default="docs/api/openapi.json",
        help="Output path for the OpenAPI JSON document.",
    )
    args = parser.parse_args()
    export_openapi(Path(args.output))


if __name__ == "__main__":
    main()
