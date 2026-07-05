from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from src.vyu.api.exceptions import ApiError
from src.vyu.auth.resolver import AuthorizationError, PrincipalResolver
from src.vyu.auth.principal import RequestPrincipal
from src.vyu.auth.settings import AuthSettings
from src.vyu.auth.tokens import (
    Hs256TokenVerifier,
    OidcJwksTokenVerifier,
    TokenVerifier,
    build_token_verifier,
    verify_authorization_header,
)
from src.vyu.deployment.http_adapter import AuthenticationError as DeploymentAuthenticationError
from src.vyu.deployment.idp import OidcJwksConfig


def get_auth_settings(request: Request) -> AuthSettings:
    settings = request.app.state.auth_settings
    assert isinstance(settings, AuthSettings)
    return settings


def get_token_verifier(request: Request) -> TokenVerifier:
    verifier = request.app.state.token_verifier
    assert isinstance(verifier, Hs256TokenVerifier | OidcJwksTokenVerifier)
    return verifier


def get_session_factory(request: Request) -> sessionmaker[Session]:
    factory = request.app.state.session_factory
    assert isinstance(factory, sessionmaker)
    return factory


def get_principal_resolver() -> PrincipalResolver:
    return PrincipalResolver()


def build_auth_runtime(auth_settings: AuthSettings) -> tuple[AuthSettings, TokenVerifier]:
    oidc_config = None
    if auth_settings.auth_mode == "oidc_jwks":
        oidc_config = OidcJwksConfig(
            issuer=auth_settings.token_issuer,
            audience=auth_settings.token_audience,
            jwks_uri=auth_settings.oidc_jwks_uri,
            jwks_path=Path(auth_settings.oidc_jwks_path)
            if auth_settings.oidc_jwks_path
            else None,
            discovery_uri=auth_settings.oidc_discovery_uri,
            required_token_use=auth_settings.oidc_required_token_use,
            require_email_verified=auth_settings.require_email_verified,
        )
    verifier = build_token_verifier(
        auth_mode=auth_settings.auth_mode,
        issuer=auth_settings.token_issuer,
        audience=auth_settings.token_audience,
        hs256_secret=auth_settings.hs256_secret,
        require_email_verified=auth_settings.require_email_verified,
        oidc_config=oidc_config,
    )
    return auth_settings, verifier


def get_request_principal(
    request: Request,
    auth_settings: Annotated[AuthSettings, Depends(get_auth_settings)],
    token_verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
    resolver: Annotated[PrincipalResolver, Depends(get_principal_resolver)],
) -> RequestPrincipal:
    try:
        verified = verify_authorization_header(
            token_verifier,
            {key: value for key, value in request.headers.items()},
        )
    except DeploymentAuthenticationError as exc:
        raise ApiError(
            status_code=401,
            code="authentication_failed",
            message=str(exc),
        ) from exc
    with session_factory.begin() as session:
        try:
            return resolver.resolve(
                verified,
                session,
                request_id=request.state.request_id,
                trace_id=request.state.trace_id,
            )
        except AuthorizationError as exc:
            raise ApiError(
                status_code=403,
                code="authorization_failed",
                message=str(exc),
            ) from exc


def get_db_session(
    request: Request,
    principal: Annotated[RequestPrincipal, Depends(get_request_principal)],
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> Generator[Session, None, None]:
    with session_factory.begin() as session:
        from src.vyu.auth.resolver import apply_principal_scope

        apply_principal_scope(session, principal)
        yield session
