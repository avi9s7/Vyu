from __future__ import annotations

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.vyu.api.errors import ErrorField, build_error_response
from src.vyu.api.dependencies import build_auth_runtime
from src.vyu.api.exceptions import ApiError
from src.vyu.api.middleware import RequestContextMiddleware
from src.vyu.api.routers.auth_debug import create_auth_debug_router
from src.vyu.api.routers.health import create_health_router, create_version_router
from src.vyu.api.settings import ApiSettings
from src.vyu.auth.settings import AuthSettings
from src.vyu.db.session import build_engine, build_session_factory
from src.vyu.db.settings import DatabaseSettings


def current_schema_revision(engine: Engine) -> str:
    with engine.connect() as connection:
        result = connection.execute(text("SELECT version_num FROM alembic_version"))
        revision = result.scalar_one()
        if not isinstance(revision, str):
            raise RuntimeError("alembic_version returned unexpected value")
        return revision


def verify_schema_revision(engine: Engine, expected: str) -> str:
    revision = current_schema_revision(engine)
    if revision != expected:
        raise RuntimeError(
            f"expected Alembic revision {expected}, found {revision}"
        )
    return revision


def create_app(
    *,
    settings_override: ApiSettings | None = None,
    database_settings_override: DatabaseSettings | None = None,
    auth_settings_override: AuthSettings | None = None,
    engine_override: Engine | None = None,
    schema_revision_override: str | None = None,
    session_factory_override: sessionmaker[Session] | None = None,
) -> FastAPI:
    api_settings = settings_override or ApiSettings()
    database_settings = database_settings_override or DatabaseSettings()
    auth_settings = auth_settings_override or AuthSettings(env=database_settings.env)
    engine = engine_override or build_engine(database_settings)
    schema_revision = schema_revision_override or verify_schema_revision(
        engine, api_settings.expected_migration_revision
    )
    auth_settings, token_verifier = build_auth_runtime(auth_settings)
    session_factory = session_factory_override or build_session_factory(engine)

    app = FastAPI(title="VYU API", version="0.1.0", openapi_url="/v1/openapi.json")
    app.state.api_settings = api_settings
    app.state.database_settings = database_settings
    app.state.auth_settings = auth_settings
    app.state.token_verifier = token_verifier
    app.state.engine = engine
    app.state.schema_revision = schema_revision
    app.state.session_factory = session_factory

    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        fields = [
            ErrorField(
                path=".".join(str(part) for part in error.get("loc", ())),
                code=error.get("type", "validation_error"),
            )
            for error in exc.errors()
        ]
        payload = build_error_response(
            request_id=request.state.request_id,
            trace_id=request.state.trace_id,
            code="validation_error",
            message="Request validation failed.",
            fields=fields,
        )
        return JSONResponse(status_code=422, content=payload)

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        payload = build_error_response(
            request_id=request.state.request_id,
            trace_id=request.state.trace_id,
            code=exc.code,
            message=exc.message,
            retryable=exc.retryable,
        )
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = "not_found" if exc.status_code == 404 else "http_error"
        payload = build_error_response(
            request_id=request.state.request_id,
            trace_id=request.state.trace_id,
            code=code,
            message="The requested resource was not found."
            if exc.status_code == 404
            else "Request failed.",
        )
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        payload = build_error_response(
            request_id=request.state.request_id,
            trace_id=request.state.trace_id,
            code="internal_error",
            message="An internal error occurred.",
        )
        return JSONResponse(status_code=500, content=payload)

    v1 = APIRouter(prefix="/v1")
    v1.include_router(create_health_router(engine=engine))
    v1.include_router(
        create_version_router(settings=api_settings, schema_revision=schema_revision)
    )
    v1.include_router(create_auth_debug_router())

    @v1.get("/debug/boom", include_in_schema=False)
    def debug_boom() -> None:
        raise RuntimeError("boom")

    class DebugValidateBody(BaseModel):
        name: str = Field(min_length=1)

    @v1.post("/debug/validate", include_in_schema=False)
    def debug_validate(body: DebugValidateBody) -> dict[str, str]:
        return {"name": body.name}

    app.include_router(v1)

    return app
