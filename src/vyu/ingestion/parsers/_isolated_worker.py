from __future__ import annotations

import json
import sys
from pathlib import Path

from src.vyu.ingestion.parsers.base import get_parser_for_filename
from src.vyu.ingestion.parsers.isolated import serialize_parse_result


def main() -> int:
    payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    input_path = Path(str(payload["input_path"]))
    output_path = Path(str(payload["output_path"]))
    filename = str(payload["filename"])
    media_type = str(payload["media_type"])
    parser = get_parser_for_filename(filename)
    result = parser.parse(input_path.read_bytes(), filename=filename, media_type=media_type)
    output_path.write_text(json.dumps(serialize_parse_result(result)), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
