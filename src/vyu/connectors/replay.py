from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.vyu.connectors.http import request_hash, response_hash
from src.vyu.research_mcp.hashing import stable_hash


@dataclass(frozen=True)
class ReplayFixture:
    schema_version: str
    source: str
    mode: str
    request_hash: str
    response_hash: str
    recorded_at: str
    license_note: str
    request: dict[str, object]
    response_payload: dict[str, Any]
    normalized: dict[str, Any]

    def to_json(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "mode": self.mode,
            "request_hash": self.request_hash,
            "response_hash": self.response_hash,
            "recorded_at": self.recorded_at,
            "license_note": self.license_note,
            "request": self.request,
            "response_payload": self.response_payload,
            "normalized": self.normalized,
        }

    @classmethod
    def from_json(cls, payload: dict[str, object]) -> ReplayFixture:
        return cls(
            schema_version=str(payload["schema_version"]),
            source=str(payload["source"]),
            mode=str(payload["mode"]),
            request_hash=str(payload["request_hash"]),
            response_hash=str(payload["response_hash"]),
            recorded_at=str(payload["recorded_at"]),
            license_note=str(payload.get("license_note", "")),
            request=dict(payload.get("request", {})),
            response_payload=dict(payload.get("response_payload", {})),
            normalized=dict(payload.get("normalized", {})),
        )

    def validate_hashes(self) -> None:
        calculated_request = request_hash(
            str(self.request.get("method", "GET")),
            str(self.request.get("url", "")),
            dict(self.request.get("params", {})),
        )
        if calculated_request != self.request_hash:
            raise ValueError("Replay fixture request hash mismatch.")
        body = json.dumps(self.response_payload, sort_keys=True).encode("utf-8")
        if response_hash(200, body) != self.response_hash:
            raise ValueError("Replay fixture response hash mismatch.")


class ReplayFixtureStore:
    def __init__(self, root: Path):
        self.root = root

    def load(self, source: str, mode: str) -> ReplayFixture:
        path = self.root / source / f"{mode}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        fixture = ReplayFixture.from_json(payload)
        fixture.validate_hashes()
        return fixture

    def write(self, fixture: ReplayFixture) -> Path:
        path = self.root / fixture.source / f"{fixture.mode}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(fixture.to_json(), indent=2, sort_keys=True), encoding="utf-8")
        return path


def build_fixture(
    *,
    source: str,
    mode: str,
    url: str,
    params: dict[str, object],
    response_payload: dict[str, Any],
    normalized: dict[str, Any],
    license_note: str = "",
) -> ReplayFixture:
    body = json.dumps(response_payload, sort_keys=True).encode("utf-8")
    return ReplayFixture(
        schema_version="connector-replay-v1",
        source=source,
        mode=mode,
        request_hash=request_hash("GET", url, params),
        response_hash=response_hash(200, body),
        recorded_at=datetime.now(timezone.utc).isoformat(),
        license_note=license_note,
        request={"method": "GET", "url": url, "params": params},
        response_payload=response_payload,
        normalized=normalized,
    )


def normalized_payload_hash(normalized: dict[str, Any]) -> str:
    return stable_hash(normalized)
