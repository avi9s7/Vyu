# Deployment HTTP Adapter

This module is the first deployment-facing HTTP boundary for Vyu.

The HTTP adapter implementation lives in `src/vyu/deployment/http_adapter.py`; enterprise OIDC/JWKS validation lives in `src/vyu/deployment/idp.py`. These modules do not start a server, choose FastAPI/Flask/Django, provision the IdP, or add deployed rate limiting. It provides a tested adapter that a future framework-specific layer can call after receiving an HTTP request.

## Module Scope

Implemented behavior:

- Accept HTTP-shaped requests through `DeploymentHttpRequest`.
- Validate `Authorization: Bearer ...` tokens before service dispatch.
- Optionally validate `x-vyu-api-key` through tenant-governed service-account/API-key records before service dispatch.
- Validate HS256 JWT shape, algorithm, signature, issuer, audience, expiry, not-before, and issued-at claims using the Python standard library for local smoke testing.
- Validate enterprise OIDC RS256 bearer JWTs against JWKS for AWS/Cognito or federated OIDC deployments.
- Allow unauthenticated health checks for configured paths such as `/v1/health`.
- Preserve or create `x-vyu-request-id` and `x-vyu-audit-correlation-id`.
- Pass authenticated claims into `ServiceRouteRequest.identity_claims`.
- Return fail-closed service-style envelopes for authentication errors.
- Delegate authenticated requests to `ServiceRouteRuntime`.

## Token Validation Contract

`Hs256BearerTokenAuthenticator` is configured with:

- `issuer`
- `audience`
- `hs256_secret`
- `leeway_seconds`
- `unauthenticated_paths`

The authenticator rejects missing Authorization headers, non-Bearer schemes, malformed JWTs, non-HS256 algorithms, invalid signatures, untrusted issuers, unaccepted audiences, expired tokens, tokens that are not valid yet, and tokens issued in the future beyond configured leeway.

`OidcJwksBearerTokenAuthenticator` is configured with issuer, audience, JWKS file/URI/discovery source, accepted algorithms, leeway, cache TTL, fetch timeout, and optional `token_use`. It rejects missing/malformed bearer tokens, algorithms outside the allow-list, missing JWKS keys, invalid RS256 signatures, untrusted issuers, unaccepted audiences, expired/not-yet-valid tokens, and disallowed Cognito-style token-use values.

## Identity Flow

```text
HTTP-shaped request
  -> CompositeDeploymentAuthenticator
  -> x-vyu-api-key via TenantGovernanceApiKeyAuthenticator, or bearer JWT via Hs256BearerTokenAuthenticator/OidcJwksBearerTokenAuthenticator
  -> trusted claim dictionary
  -> ServiceRouteRequest.identity_claims
  -> IdentityMapper
  -> internal Vyu identity headers
  -> route runtime dispatch
```

The adapter does not trust client-supplied `x-vyu-user-id`, `x-vyu-tenant-id`, `x-vyu-workspace-id`, or `x-vyu-role`. When the downstream service runtime has an `IdentityMapper`, trusted claims overwrite those fields before the route runtime sees the request.

## Current Limits

- HS256 support is intentionally local and stdlib-only for smoke/testing.
- OIDC/JWKS validation is implemented for RS256; direct SAML XML processing should be brokered through Cognito/OIDC.
- Token revocation, session state, nonce tracking, and MFA are not implemented here. Break-glass entitlement is enforced by tenant governance after authentication.
- No framework response objects are created here.
- No server startup, TLS, CORS, CSRF, request-size limits, or rate limiting are implemented here.
