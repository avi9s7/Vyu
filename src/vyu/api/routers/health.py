from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.engine import Engine
from starlette.responses import Response

from src.vyu.api.errors import build_error_response
from src.vyu.api.settings import ApiSettings


def create_health_router(*, engine: Engine) -> APIRouter:
    router = APIRouter(prefix="/health", tags=["health"])

    @router.get("/live")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/ready", response_model=None)
    def ready(request: Request) -> Response:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception:
            payload = build_error_response(
                request_id=request.state.request_id,
                trace_id=request.state.trace_id,
                code="dependency_unavailable",
                message="Database is unavailable.",
                retryable=True,
            )
            return JSONResponse(status_code=503, content=payload)
        return JSONResponse(content={"status": "ready"})

    return router


def create_version_router(*, settings: ApiSettings, schema_revision: str) -> APIRouter:
    router = APIRouter(tags=["meta"])

    @router.get("/version")
    def version() -> dict[str, str | None]:
        return {
            "service": settings.service_name,
            "environment": settings.env,
            "git_sha": settings.git_sha,
            "image_digest": settings.image_digest,
            "schema_revision": schema_revision,
        }

    return router
