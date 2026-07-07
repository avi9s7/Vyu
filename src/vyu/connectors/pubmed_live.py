from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

from src.vyu.connectors.audit import JsonlTransportAuditSink, TransportAuditRecord
from src.vyu.connectors.http import ConnectorHttpClient, HttpClientConfig, request_hash, response_hash
from src.vyu.connectors.replay import ReplayFixtureStore
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
        http_client: ConnectorHttpClient | None = None,
        transport_audit_sink: JsonlTransportAuditSink | None = None,
    ):
        if not tool:
            raise ValueError("PubMed transport requires a non-empty NCBI tool name.")
        if not email:
            raise ValueError("PubMed transport requires a contact email.")
        self.tool = tool
        self.email = email
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.opener = opener
        self.runtime = runtime
        self.transport_audit_sink = transport_audit_sink
        if http_client is not None:
            self.http_client = http_client
        elif opener is None:
            config = HttpClientConfig(read_timeout_seconds=timeout_seconds)
            self.http_client = ConnectorHttpClient(config=config)
        else:
            self.http_client = None

    def __call__(self, url: str, params: dict[str, object]) -> dict[str, Any]:
        mode = str(params["mode"])
        query_url = self._query_url(url, params)
        request_params = self._request_params(params)

        def operation() -> dict[str, Any]:
            if self.opener is not None:
                body = self.opener(query_url, self.timeout_seconds)
                if mode == "fetch":
                    payload = {"xml": body.decode("utf-8")}
                else:
                    payload = json.loads(body.decode("utf-8"))
                status_code = 200
                elapsed_seconds = 0.0
                provider_request_id = None
            else:
                assert self.http_client is not None
                response = self.http_client.get(url, params=request_params)
                if mode == "fetch":
                    payload = {"xml": response.body.decode("utf-8")}
                else:
                    payload = response.json()
                status_code = response.status_code
                elapsed_seconds = response.elapsed_seconds
                provider_request_id = response.provider_request_id
                body = response.body

            if mode == "fetch":
                normalized = payload
            elif mode == "search":
                normalized = _normalize_esearch(payload)
            elif mode == "summary":
                normalized = _normalize_esummary(payload)
            else:
                raise ValueError(f"Unsupported PubMed transport mode: {mode}")
            self._audit_transport(
                mode=mode,
                query_url=query_url,
                request_params=request_params,
                body=body,
                status_code=status_code,
                elapsed_seconds=elapsed_seconds,
                provider_request_id=provider_request_id,
                result_count=_result_count(normalized),
            )
            return normalized

        if self.runtime is None:
            return operation()
        result = self.runtime.run("pubmed", mode, operation)
        return result.value

    def _request_params(self, params: dict[str, object]) -> dict[str, object]:
        mode = str(params["mode"])
        query_params = {
            key: value
            for key, value in params.items()
            if key not in {"mode", "ids"}
        }
        if "ids" in params:
            query_params["id"] = params["ids"]
        query_params["retmode"] = "json" if mode != "fetch" else "xml"
        if mode == "fetch":
            query_params["rettype"] = "abstract"
        query_params["tool"] = self.tool
        query_params["email"] = self.email
        if self.api_key:
            query_params["api_key"] = self.api_key
        return query_params

    def _query_url(self, url: str, params: dict[str, object]) -> str:
        return f"{url}?{urlencode(self._request_params(params))}"

    def _audit_transport(
        self,
        *,
        mode: str,
        query_url: str,
        request_params: dict[str, object],
        body: bytes,
        status_code: int,
        elapsed_seconds: float,
        provider_request_id: str | None,
        result_count: int,
    ) -> None:
        if self.transport_audit_sink is None:
            return
        self.transport_audit_sink.append(
            TransportAuditRecord(
                source="pubmed",
                action=mode,
                request_hash=request_hash("GET", query_url.split("?", 1)[0], request_params),
                response_hash=response_hash(status_code, body),
                status_code=status_code,
                result_count=result_count,
                latency_ms=elapsed_seconds * 1000.0,
                attempts=1,
                provider_request_id=provider_request_id,
            )
        )


class PubMedReplayTransport:
    def __init__(self, fixture_path: Path, *, fixture_store: ReplayFixtureStore | None = None):
        self.fixture_path = fixture_path
        self.fixture_store = fixture_store
        if fixture_store is not None:
            self.payload = {
                "search": fixture_store.load("pubmed", "search").normalized,
                "summary": fixture_store.load("pubmed", "summary").normalized,
            }
        else:
            self.payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    def __call__(self, _url: str, params: dict[str, object]) -> dict[str, Any]:
        mode = str(params["mode"])
        try:
            return self.payload[mode]
        except KeyError as exc:
            raise KeyError(f"Replay fixture {self.fixture_path} has no {mode!r} payload.") from exc


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


def _result_count(normalized: dict[str, Any]) -> int:
    if "ids" in normalized:
        return len(normalized["ids"])
    if "xml" in normalized:
        return normalized["xml"].count("<PubmedArticle>")
    return len(normalized.get("documents", []))
