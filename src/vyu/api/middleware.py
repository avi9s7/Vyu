from __future__ import annotations

import re
import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "x-request-id"
TRACE_ID_HEADER = "x-trace-id"
SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        *,
        logger: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(app)
        self._logger = logger or (lambda _message: None)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "").strip()
        request_id = incoming if SAFE_REQUEST_ID.fullmatch(incoming or "") else str(uuid.uuid4())
        trace_id = request.headers.get(TRACE_ID_HEADER, request_id)
        request.state.request_id = request_id
        request.state.trace_id = trace_id
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers[TRACE_ID_HEADER] = trace_id
        self._logger(
            f"method={request.method} path={request.url.path} status={response.status_code} "
            f"duration_ms={duration_ms:.2f} request_id={request_id}"
        )
        return response
