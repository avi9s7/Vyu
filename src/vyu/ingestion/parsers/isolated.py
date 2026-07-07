from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from src.vyu.ingestion.parsers.base import ParseResult, get_parser_for_filename

_DEFAULT_TIMEOUT_SECONDS = 60.0


def run_isolated_parse(
    data: bytes,
    *,
    filename: str,
    media_type: str,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
) -> ParseResult:
    with tempfile.TemporaryDirectory(prefix="vyu-parse-") as temp_dir:
        input_path = Path(temp_dir) / "input.bin"
        output_path = Path(temp_dir) / "result.json"
        input_path.write_bytes(data)
        payload = {
            "input_path": str(input_path),
            "output_path": str(output_path),
            "filename": filename,
            "media_type": media_type,
        }
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "src.vyu.ingestion.parsers._isolated_worker"],
                input=json.dumps(payload).encode("utf-8"),
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ParseResult.failed(
                parser_name="vyu_isolated",
                parser_version="1.0.0",
                code="parser_timeout",
                message="Parser subprocess exceeded the configured timeout.",
            )
        if completed.returncode != 0 or not output_path.exists():
            stderr = completed.stderr.decode("utf-8", errors="replace").strip()
            message = stderr or "Parser subprocess failed."
            return ParseResult.failed(
                parser_name="vyu_isolated",
                parser_version="1.0.0",
                code="malformed_document",
                message=message,
            )
        result_payload = json.loads(output_path.read_text(encoding="utf-8"))
        return _parse_result_from_payload(result_payload)


def parse_in_process(
    data: bytes,
    *,
    filename: str,
    media_type: str,
) -> ParseResult:
    parser = get_parser_for_filename(filename)
    return parser.parse(data, filename=filename, media_type=media_type)


def _parse_result_from_payload(payload: dict[str, object]) -> ParseResult:
    from src.vyu.ingestion.parsers.base import ParsedDocument

    parser_name = str(payload.get("parser_name", "vyu_unknown"))
    parser_version = str(payload.get("parser_version", "0.0.0"))
    failure_payload = payload.get("failure")
    if isinstance(failure_payload, dict):
        return ParseResult.failed(
            parser_name=parser_name,
            parser_version=parser_version,
            code=str(failure_payload.get("code", "malformed_document")),
            message=str(failure_payload.get("message", "Parser failed.")),
        )
    document_payload = payload.get("document")
    if isinstance(document_payload, dict):
        return ParseResult.success(
            parser_name=parser_name,
            parser_version=parser_version,
            document=ParsedDocument.from_dict(document_payload),
        )
    return ParseResult.failed(
        parser_name=parser_name,
        parser_version=parser_version,
        code="malformed_document",
        message="Parser subprocess returned an invalid payload.",
    )


def serialize_parse_result(result: ParseResult) -> dict[str, object]:
    payload: dict[str, object] = {
        "parser_name": result.parser_name,
        "parser_version": result.parser_version,
    }
    if result.failure is not None:
        payload["failure"] = {
            "code": result.failure.code,
            "message": result.failure.message,
        }
    elif result.document is not None:
        payload["document"] = result.document.to_dict()
    return payload
