from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import urlopen

from src.vyu.connectors.runtime import ConnectorRuntime


HttpOpener = Callable[[str, float], bytes]


class PubMedHttpTransport:
    def __init__(
        self,
        tool: str,
        email: str,
        api_key: str | None = None,
        timeout_seconds: float = 10.0,
        opener: HttpOpener | None = None,
        runtime: ConnectorRuntime | None = None,
    ):
        self.tool = tool
        self.email = email
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.opener = opener or _urlopen_bytes
        self.runtime = runtime

    def __call__(self, url: str, params: dict[str, object]) -> dict[str, Any]:
        mode = str(params["mode"])
        query_url = self._query_url(url, params)

        def operation() -> dict[str, Any]:
            payload = json.loads(self.opener(query_url, self.timeout_seconds).decode("utf-8"))
            if mode == "search":
                return _normalize_esearch(payload)
            if mode == "summary":
                return _normalize_esummary(payload)
            raise ValueError(f"Unsupported PubMed transport mode: {mode}")

        if self.runtime is None:
            return operation()
        return self.runtime.run("pubmed", mode, operation).value

    def _query_url(self, url: str, params: dict[str, object]) -> str:
        query_params = {
            key: value
            for key, value in params.items()
            if key not in {"mode", "ids"}
        }
        if "ids" in params:
            query_params["id"] = params["ids"]
        query_params["retmode"] = "json"
        query_params["tool"] = self.tool
        query_params["email"] = self.email
        if self.api_key:
            query_params["api_key"] = self.api_key
        return f"{url}?{urlencode(query_params)}"


class PubMedReplayTransport:
    def __init__(self, fixture_path: Path):
        self.fixture_path = fixture_path
        self.payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    def __call__(self, _url: str, params: dict[str, object]) -> dict[str, Any]:
        mode = str(params["mode"])
        try:
            return self.payload[mode]
        except KeyError as exc:
            raise KeyError(f"Replay fixture {self.fixture_path} has no {mode!r} payload.") from exc


def _urlopen_bytes(url: str, timeout_seconds: float) -> bytes:
    with urlopen(url, timeout=timeout_seconds) as response:
        return response.read()


def _normalize_esearch(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "ids": [
            str(identifier)
            for identifier in payload.get("esearchresult", {}).get("idlist", [])
        ]
    }


def _normalize_esummary(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result", {})
    documents = [
        result[uid]
        for uid in result.get("uids", [])
        if uid in result and isinstance(result[uid], dict)
    ]
    return {"documents": documents}
