# Deployment Operator Config

This document defines the local deployment operator configuration template for Vyu.

The checked-in local template is `config/deployment.local.example.env`; the AWS Cognito/OIDC example overlay is `config/deployment.aws.cognito.example.env`. The parser and validator live in `src/vyu/deployment/operator_config.py`, and the validation command is `scripts/validate_deployment_config.py`.

## Operator Config Contract

The operator config is a `.env`-style file that can feed both:

- `DeploymentCompositionConfig` for local runtime assembly.
- `DeploymentSmokeTestConfig` for `scripts/smoke_test_deployment.py`.

The parser is intentionally dependency-free. It supports comments, `KEY=value`, `export KEY=value`, and simple single- or double-quoted values. It does not read process environment variables by itself.

Required fields:

| Key | Meaning |
| --- | --- |
| `VYU_SQLITE_DB` | Local SQLite production-shaped store path. |
| `VYU_PHASE_OUTPUT_DIR` | Local phase-output directory used by report export artifact loading. |
| `VYU_TOKEN_ISSUER` | Trusted issuer for bearer-token validation. |
| `VYU_TOKEN_AUDIENCE` | Accepted bearer-token audience. |
| `VYU_HS256_SECRET` | Required only when `VYU_AUTH_MODE=hs256`; local-only smoke/composition secret. |
| `VYU_TENANT_ID` | Tenant scope used by smoke-test reviewer queue access. |
| `VYU_WORKSPACE_ID` | Workspace scope used by smoke-test reviewer queue access. |

Optional fields:

| Key | Default | Meaning |
| --- | --- | --- |
| `VYU_AUTH_MODE` | `hs256` | Authentication mode. Use `hs256` for local smoke tests or `oidc_jwks` for AWS enterprise IdP JWT validation. |
| `VYU_OIDC_JWKS_URI` | empty | Remote JWKS endpoint for `oidc_jwks` mode. |
| `VYU_OIDC_JWKS_FILE` | empty | Mounted/static JWKS file for `oidc_jwks` mode. |
| `VYU_OIDC_DISCOVERY_URI` | empty | OIDC discovery document used to resolve `jwks_uri`. |
| `VYU_OIDC_ALLOWED_ALGORITHMS` | `RS256` | Comma-separated accepted JWT signing algorithms. Current implementation supports `RS256`. |
| `VYU_OIDC_REQUIRED_TOKEN_USE` | empty | Optional Cognito-style `token_use` requirement, such as `id`. |
| `VYU_OIDC_JWKS_CACHE_TTL_SECONDS` | `300` | Remote JWKS cache TTL. |
| `VYU_OIDC_FETCH_TIMEOUT_SECONDS` | `2.0` | Remote JWKS/discovery fetch timeout. |
| `VYU_USER_ID` | `smoke-user` | Local smoke-test user subject. |
| `VYU_ROLE` | `vyu:reviewer` | Local smoke-test role claim. |
| `VYU_TOKEN_LEEWAY_SECONDS` | `60` | Clock-skew leeway for composed token validation. |
| `VYU_TOKEN_LIFETIME_SECONDS` | `300` | Lifetime for the locally created smoke-test token. |
| `VYU_UNAUTHENTICATED_PATHS` | `/v1/health` | Comma-separated paths allowed without authentication. |
| `VYU_INITIALIZE_STORAGE` | `true` | Whether composition initializes local SQLite schema. |
| `VYU_REQUIRE_EMAIL_VERIFIED` | `false` | Whether identity mapping requires verified email. |
| `VYU_TENANT_GOVERNANCE_REGISTRY` | empty | JSON registry path for tenants, workspaces, grants, service accounts, and API keys. |
| `VYU_REQUIRE_TENANT_GOVERNANCE` | `false` | Fail closed during composition when tenant governance is not configured. The checked-in example enables this. |
| `VYU_API_KEY_AUTH_ENABLED` | `false` | Enable `x-vyu-api-key` service-account authentication through tenant governance. |
| `VYU_API_KEY_ISSUER` | `vyu-api-key` | Internal issuer used for API-key-derived service-account claims. |
| `VYU_IDENTITY_ACCESS_AUDIT_ENABLED` | `true` | Persist identity access decisions and tenant-admin lifecycle actions to production audit storage. |
| `VYU_REQUEST_ID_PREFIX` | `local-deployment` | Fallback request ID prefix. |
| `VYU_SERVERLESS_DEFAULT_REQUEST_ID` | `local-serverless` | Fallback request ID for malformed serverless events. |
| `VYU_SERVERLESS_EXTRA_RESPONSE_HEADERS` | empty | Comma-separated `key=value` response headers added by the serverless handler. |

## Safe Validation

Validate the checked-in example template without treating its placeholder secret as production-ready:

```bash
python scripts/validate_deployment_config.py --env-file config/deployment.local.example.env --allow-placeholder-secret
```

Validate a copied local config that must contain a real local-only secret:

```bash
python scripts/validate_deployment_config.py --env-file config/deployment.local.env
```

The validation output uses `DeploymentOperatorConfig.safe_summary()` and never prints the configured secret value. It only reports whether a secret is configured and whether it still looks like a placeholder.

## Smoke Test Usage

After copying `config/deployment.local.example.env` to a local untracked file and replacing `VYU_HS256_SECRET`, the smoke-test command can read the same file:

```bash
python scripts/smoke_test_deployment.py --env-file config/deployment.local.env
```

This command still performs the same three checks documented in `docs/production/deployment-smoke-test.md`: `health`, `authenticated_review_queue`, and `fail_closed_bad_token`.

## Secret Handling Rules

- Do not commit real `VYU_HS256_SECRET` values.
- Do not use the example placeholder outside template validation.
- Do not treat local HS256 secrets as production identity-provider configuration.
- Use `VYU_AUTH_MODE=oidc_jwks` with Amazon Cognito or another approved OIDC/JWKS issuer for AWS production. The Cognito Terraform stack emits the required `VYU_TOKEN_ISSUER`, `VYU_TOKEN_AUDIENCE`, `VYU_OIDC_JWKS_URI`, and `VYU_OIDC_DISCOVERY_URI` values through its `vyu_operator_env` output.

## Current Limits

- This module does not manage secret storage, rotation, vault integration, or cloud deployment variables.
- Cognito identity-provider provisioning is available in `deploy/aws/cognito`, with `scripts/render_cognito_operator_env.py` to render the OIDC settings into an operator env overlay.
- It does not apply Kubernetes, Lambda, ECS, Cloud Run, API Gateway, WAF, Route 53, ACM, or container runtime settings.
- It does not validate rate-limit, CORS, WAF, TLS, or cloud IAM controls.

## Next Module Boundary

The next deployment module should add a first deployment packaging manifest or app-entrypoint example that consumes the operator config while keeping real cloud infrastructure and production identity-provider details outside the core domain route runtimes.
