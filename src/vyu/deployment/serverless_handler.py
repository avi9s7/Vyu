from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Mapping, Protocol

from src.vyu.deployment.api_service import (
    DeploymentApiServiceShell,
    DeploymentHttpHandler,
    FrameworkRequestError,
)


class ServerlessEventHandler(Protocol):
    def handle_serverless_event(self, event: Mapping[str, object]) -> dict[str, object]:
        ...


@dataclass(frozen=True)
class ServerlessHandlerConfig:
    default_request_id: str = "serverless-request"
    include_exception_details: bool = False
    extra_response_headers: dict[str, str] = field(default_factory=dict)


class ServerlessDeploymentHandler:
    """Callable serverless handler for API Gateway-style HTTP events."""

    def __init__(
        self,
        service_shell: ServerlessEventHandler,
        config: ServerlessHandlerConfig | None = None,
    ) -> None:
        self.service_shell = service_shell
        self.config = config or ServerlessHandlerConfig()

    def __call__(self, event: object, context: object | None = None) -> dict[str, object]:
        return self.handle(event, context)

    def handle(self, event: object, context: object | None = None) -> dict[str, object]:
        del context
        if not isinstance(event, Mapping):
            return self._error_response(
                status_code=400,
                event={},
                reason="serverless_request_invalid",
                detail="Serverless handler event must be a mapping.",
            )
        try:
            response = self.service_shell.handle_serverless_event(event)
        except FrameworkRequestError as exc:
            return self._error_response(
                status_code=400,
                event=event,
                reason="serverless_request_invalid",
                detail=str(exc),
            )
        except Exception as exc:  # pragma: no cover - concrete failures vary by deployment.
            detail = (
                str(exc)
                if self.config.include_exception_details
                else "Unhandled serverless handler error."
            )
            return self._error_response(
                status_code=500,
                event=event,
                reason="serverless_handler_error",
                detail=detail,
            )
        return _with_extra_headers(response, self.config.extra_response_headers)

    def _error_response(
        self,
        status_code: int,
        event: Mapping[str, object],
        reason: str,
        detail: str,
    ) -> dict[str, object]:
        request_id = _request_id_from_event(event) or self.config.default_request_id
        headers = {
            "content-type": "application/json",
            "x-vyu-request-id": request_id,
            **self.config.extra_response_headers,
        }
        body = {
            "request_id": request_id,
            "audit_correlation_id": request_id,
            "status": "error",
            "reason": reason,
            "error": {
                "reason": reason,
                "detail": detail,
            },
            "data": {
                "reason": reason,
                "detail": detail,
            },
        }
        return {
            "statusCode": status_code,
            "headers": headers,
            "body": json.dumps(body, separators=(",", ":"), sort_keys=True),
            "isBase64Encoded": False,
        }


def serverless_handler_from_deployment_handler(
    deployment_handler: DeploymentHttpHandler,
    config: ServerlessHandlerConfig | None = None,
) -> ServerlessDeploymentHandler:
    return ServerlessDeploymentHandler(
        service_shell=DeploymentApiServiceShell(deployment_handler),
        config=config,
    )


def _with_extra_headers(
    response: Mapping[str, object],
    extra_headers: Mapping[str, str],
) -> dict[str, object]:
    copied = dict(response)
    headers = {
        str(key): str(value)
        for key, value in dict(copied.get("headers", {})).items()
    }
    headers.update({str(key): str(value) for key, value in extra_headers.items()})
    copied["headers"] = headers
    return copied


def _request_id_from_event(event: Mapping[str, object]) -> str | None:
    headers = event.get("headers")
    if isinstance(headers, Mapping):
        normalized = {str(key).lower(): str(value) for key, value in headers.items()}
        request_id = normalized.get("x-vyu-request-id")
        if request_id:
            return request_id
    request_context = event.get("requestContext")
    if isinstance(request_context, Mapping):
        request_id = request_context.get("requestId")
        if request_id:
            return str(request_id)
    return None
