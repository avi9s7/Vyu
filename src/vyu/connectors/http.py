from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx


def _stable_hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class HttpClientConfig:
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 10.0
    write_timeout_seconds: float = 5.0
    pool_timeout_seconds: float = 5.0
    max_response_bytes: int = 5_000_000
    allowed_hosts: frozenset[str] = frozenset({"eutils.ncbi.nlm.nih.gov"})
    user_agent: str = "vyu-connector/1.0"
    follow_redirects: bool = True
    max_redirects: int = 3

    @property
    def timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.connect_timeout_seconds,
            read=self.read_timeout_seconds,
            write=self.write_timeout_seconds,
            pool=self.pool_timeout_seconds,
        )


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes
    elapsed_seconds: float
    final_url: str
    provider_request_id: str | None = None

    def json(self) -> Any:
        try:
            return json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HttpClientError(
                "invalid_json",
                status_code=self.status_code,
                message="Response body is not valid JSON.",
            ) from exc


class HttpClientError(Exception):
    def __init__(
        self,
        error_code: str,
        *,
        status_code: int | None = None,
        message: str = "",
        retry_after_seconds: float | None = None,
        provider_request_id: str | None = None,
    ):
        super().__init__(message or error_code)
        self.error_code = error_code
        self.status_code = status_code
        self.message = message
        self.retry_after_seconds = retry_after_seconds
        self.provider_request_id = provider_request_id


def request_hash(method: str, url: str, params: dict[str, object] | None = None) -> str:
    return _stable_hash(
        {
            "method": method.upper(),
            "url": url,
            "params": params or {},
        }
    )


def response_hash(status_code: int, body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


class ConnectorHttpClient:
    def __init__(
        self,
        config: HttpClientConfig | None = None,
        client: httpx.Client | None = None,
    ):
        self.config = config or HttpClientConfig()
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=self.config.timeout,
            follow_redirects=self.config.follow_redirects,
            max_redirects=self.config.max_redirects,
            verify=True,
            headers={"User-Agent": self.config.user_agent},
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> ConnectorHttpClient:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def get(self, url: str, *, params: dict[str, object] | None = None) -> HttpResponse:
        self._validate_url(url)
        query_params = {key: str(value) for key, value in (params or {}).items()}
        try:
            response = self._client.get(
                url,
                params=query_params,
                headers={"User-Agent": self.config.user_agent},
            )
        except httpx.TimeoutException as exc:
            raise HttpClientError("timeout", message=str(exc)) from exc
        except httpx.ConnectError as exc:
            raise HttpClientError("connection_reset", message=str(exc)) from exc
        except httpx.RequestError as exc:
            raise HttpClientError("request_error", message=str(exc)) from exc

        final_url = str(response.url)
        self._validate_url(final_url)
        body = response.read()
        response.close()
        elapsed_seconds = _response_elapsed_seconds(response)
        if len(body) > self.config.max_response_bytes:
            raise HttpClientError(
                "oversized_response",
                status_code=response.status_code,
                message=f"Response exceeded {self.config.max_response_bytes} bytes.",
            )

        http_response = HttpResponse(
            status_code=response.status_code,
            headers={key.lower(): value for key, value in response.headers.items()},
            body=body,
            elapsed_seconds=elapsed_seconds,
            final_url=final_url,
            provider_request_id=response.headers.get("x-request-id")
            or response.headers.get("x-amzn-requestid"),
        )
        self._validate_status(http_response)
        return http_response

    def _validate_url(self, url: str) -> None:
        host = urlparse(url).hostname
        if host is None or host not in self.config.allowed_hosts:
            raise HttpClientError(
                "host_not_allowed",
                message=f"Host {host!r} is not in the connector allowlist.",
            )

    def _validate_status(self, response: HttpResponse) -> None:
        if 200 <= response.status_code < 300:
            return
        retry_after = _parse_retry_after(response.headers.get("retry-after"))
        if response.status_code == 429:
            raise HttpClientError(
                "rate_limited",
                status_code=429,
                message="Upstream rate limit exceeded.",
                retry_after_seconds=retry_after,
                provider_request_id=response.provider_request_id,
            )
        if response.status_code >= 500:
            raise HttpClientError(
                "server_error",
                status_code=response.status_code,
                message=f"Upstream server error {response.status_code}.",
                retry_after_seconds=retry_after,
                provider_request_id=response.provider_request_id,
            )
        raise HttpClientError(
            "client_error",
            status_code=response.status_code,
            message=f"Non-retryable client error {response.status_code}.",
            provider_request_id=response.provider_request_id,
        )


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _response_elapsed_seconds(response: httpx.Response) -> float:
    try:
        return response.elapsed.total_seconds()
    except RuntimeError:
        return 0.0
