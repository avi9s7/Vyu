from __future__ import annotations

import base64
from dataclasses import dataclass, field
import inspect
import json
from typing import Mapping, Protocol
from urllib.parse import parse_qsl

from src.vyu.deployment.http_adapter import (
    DeploymentHttpRequest,
    DeploymentHttpResponse,
)


class FrameworkRequestError(ValueError):
    """Raised when a framework request cannot be converted safely."""


class DeploymentHttpHandler(Protocol):
    def handle(self, request: DeploymentHttpRequest) -> DeploymentHttpResponse:
        ...


@dataclass(frozen=True)
class FrameworkHttpResponse:
    status_code: int
    body: dict[str, object]
    headers: dict[str, str] = field(default_factory=dict)

    def as_json_response_kwargs(self) -> dict[str, object]:
        return {
            "status_code": self.status_code,
            "content": dict(self.body),
            "headers": dict(self.headers),
        }


class DeploymentApiServiceShell:
    """Dependency-free framework/serverless shell around the deployment HTTP adapter."""

    def __init__(self, deployment_handler: DeploymentHttpHandler) -> None:
        self.deployment_handler = deployment_handler

    async def handle_fastapi_request(self, request: object) -> FrameworkHttpResponse:
        deployment_request = await deployment_request_from_fastapi(request)
        deployment_response = self.deployment_handler.handle(deployment_request)
        return framework_response_from_deployment(deployment_response)

    def handle_flask_request(self, request: object) -> FrameworkHttpResponse:
        deployment_request = deployment_request_from_flask(request)
        deployment_response = self.deployment_handler.handle(deployment_request)
        return framework_response_from_deployment(deployment_response)

    def handle_serverless_request(self, event: Mapping[str, object]) -> DeploymentHttpResponse:
        deployment_request = deployment_request_from_serverless_event(event)
        return self.deployment_handler.handle(deployment_request)

    def handle_serverless_event(self, event: Mapping[str, object]) -> dict[str, object]:
        deployment_response = self.handle_serverless_request(event)
        return serverless_response_from_deployment(deployment_response)


async def deployment_request_from_fastapi(request: object) -> DeploymentHttpRequest:
    json_body = await _read_fastapi_json_body(request)
    return DeploymentHttpRequest(
        method=_require_text(getattr(request, "method", None), "method"),
        path=_path_from_fastapi_request(request),
        headers=_string_mapping(getattr(request, "headers", {})),
        query=_query_mapping(getattr(request, "query_params", {})),
        json_body=json_body,
    )


def deployment_request_from_flask(request: object) -> DeploymentHttpRequest:
    return DeploymentHttpRequest(
        method=_require_text(getattr(request, "method", None), "method"),
        path=_require_text(getattr(request, "path", None), "path"),
        headers=_string_mapping(getattr(request, "headers", {})),
        query=_query_mapping(getattr(request, "args", {})),
        json_body=_read_flask_json_body(request),
    )


def deployment_request_from_serverless_event(
    event: Mapping[str, object],
) -> DeploymentHttpRequest:
    return DeploymentHttpRequest(
        method=_serverless_method(event),
        path=_serverless_path(event),
        headers=_string_mapping(_mapping_or_empty(event.get("headers"))),
        query=_serverless_query(event),
        json_body=_serverless_json_body(event),
    )


def framework_response_from_deployment(response: DeploymentHttpResponse) -> FrameworkHttpResponse:
    return FrameworkHttpResponse(
        status_code=response.status_code,
        body=dict(response.body),
        headers=dict(response.headers),
    )


def serverless_response_from_deployment(response: DeploymentHttpResponse) -> dict[str, object]:
    headers = {"content-type": "application/json"}
    headers.update({str(key): str(value) for key, value in response.headers.items()})
    return {
        "statusCode": response.status_code,
        "headers": headers,
        "body": json.dumps(response.body, separators=(",", ":"), sort_keys=True),
        "isBase64Encoded": False,
    }


async def _read_fastapi_json_body(request: object) -> dict[str, object]:
    json_method = getattr(request, "json", None)
    if json_method is None:
        return {}
    try:
        maybe_body = json_method()
        body = await maybe_body if inspect.isawaitable(maybe_body) else maybe_body
    except Exception as exc:  # pragma: no cover - framework exception types vary.
        raise FrameworkRequestError("Request JSON body could not be parsed.") from exc
    return _json_object(body)


def _read_flask_json_body(request: object) -> dict[str, object]:
    get_json = getattr(request, "get_json", None)
    if get_json is not None:
        try:
            body = get_json(silent=True)
        except TypeError:
            body = get_json()
        except Exception as exc:  # pragma: no cover - framework exception types vary.
            raise FrameworkRequestError("Request JSON body could not be parsed.") from exc
        return _json_object(body)
    return _json_object(getattr(request, "json", None))


def _serverless_json_body(event: Mapping[str, object]) -> dict[str, object]:
    raw_body = event.get("body")
    if raw_body in (None, ""):
        return {}
    if isinstance(raw_body, Mapping):
        return _json_object(raw_body)
    if not isinstance(raw_body, str):
        raise FrameworkRequestError("Serverless event body must be a JSON string or object.")
    if bool(event.get("isBase64Encoded")):
        try:
            raw_body = base64.b64decode(raw_body).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise FrameworkRequestError(
                "Serverless event body is not valid base64 JSON text."
            ) from exc
    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise FrameworkRequestError("Serverless event body is not valid JSON.") from exc
    return _json_object(parsed)


def _json_object(body: object) -> dict[str, object]:
    if body is None:
        return {}
    if not isinstance(body, Mapping):
        raise FrameworkRequestError("Request JSON body must be an object.")
    return {str(key): value for key, value in body.items()}


def _path_from_fastapi_request(request: object) -> str:
    url = getattr(request, "url", None)
    path = getattr(url, "path", None)
    if path:
        return str(path)
    scope = getattr(request, "scope", None)
    if isinstance(scope, Mapping) and scope.get("path"):
        return str(scope["path"])
    return _require_text(getattr(request, "path", None), "path")


def _serverless_method(event: Mapping[str, object]) -> str:
    http_method = event.get("httpMethod")
    if http_method:
        return str(http_method)
    request_context = event.get("requestContext")
    if isinstance(request_context, Mapping):
        http = request_context.get("http")
        if isinstance(http, Mapping) and http.get("method"):
            return str(http["method"])
    raise FrameworkRequestError("Serverless event is missing an HTTP method.")


def _serverless_path(event: Mapping[str, object]) -> str:
    for key in ("rawPath", "path"):
        value = event.get(key)
        if value:
            return str(value)
    request_context = event.get("requestContext")
    if isinstance(request_context, Mapping):
        http = request_context.get("http")
        if isinstance(http, Mapping) and http.get("path"):
            return str(http["path"])
    raise FrameworkRequestError("Serverless event is missing a request path.")


def _serverless_query(event: Mapping[str, object]) -> dict[str, str]:
    query_params = event.get("queryStringParameters")
    if isinstance(query_params, Mapping):
        return _query_mapping(query_params)
    raw_query = event.get("rawQueryString")
    if isinstance(raw_query, str) and raw_query:
        return {
            str(key): str(value)
            for key, value in parse_qsl(raw_query, keep_blank_values=True)
        }
    return {}


def _mapping_or_empty(value: object) -> Mapping[object, object]:
    return value if isinstance(value, Mapping) else {}


def _string_mapping(value: object) -> dict[str, str]:
    mapping = _mapping_like_items(value)
    return {str(key): str(val) for key, val in mapping.items()}


def _query_mapping(value: object) -> dict[str, str]:
    mapping = _mapping_like_items(value)
    return {str(key): str(val) for key, val in mapping.items()}


def _mapping_like_items(value: object) -> Mapping[object, object]:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            converted = to_dict(flat=True)
        except TypeError:
            converted = to_dict()
        if isinstance(converted, Mapping):
            return converted
    items = getattr(value, "items", None)
    if callable(items):
        return dict(items())
    return {}


def _require_text(value: object, name: str) -> str:
    if value is None or str(value) == "":
        raise FrameworkRequestError(f"Framework request is missing {name}.")
    return str(value)
