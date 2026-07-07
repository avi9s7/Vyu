from __future__ import annotations

import hashlib
import json

from src.vyu.ingestion.chunking import CHUNKER_NAME, CHUNKER_VERSION
from src.vyu.ingestion.parsers.base import ParsedDocument


def build_normalized_document_bytes(
    parsed: ParsedDocument,
    *,
    parser_name: str,
    parser_version: str,
    chunker_name: str = CHUNKER_NAME,
    chunker_version: str = CHUNKER_VERSION,
) -> tuple[bytes, str]:
    payload = {
        "schema_version": 1,
        "parser_name": parser_name,
        "parser_version": parser_version,
        "chunker_name": chunker_name,
        "chunker_version": chunker_version,
        "document": parsed.to_dict(),
    }
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return body, hashlib.sha256(body).hexdigest()
