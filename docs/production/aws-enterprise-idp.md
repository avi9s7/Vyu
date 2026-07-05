# AWS Enterprise IdP Integration

## Purpose

Vyu now supports a real enterprise identity-provider boundary for AWS-hosted deployments through OIDC bearer JWT validation against JWKS. This lets an AWS deployment use Amazon Cognito as the native user pool or as an enterprise federation broker for SAML/OIDC providers such as Okta, Azure AD/Entra ID, or other customer IdPs.

The implementation lives in `src/vyu/deployment/idp.py` and is wired into deployment composition through `VYU_AUTH_MODE=oidc_jwks`.

## Supported Production Pattern

Recommended AWS pattern:

1. Provision Amazon Cognito with `deploy/aws/cognito`, or adapt that stack into the production Terraform root module.
2. Use Cognito as the native user pool and/or broker enterprise SAML/OIDC providers into Cognito.
3. Configure the IdP/Cognito app client to issue JWTs with Vyu-required claims:
   - `sub`
   - `iss`
   - `aud` or Cognito-style `client_id`
   - `email`
   - `email_verified` when required
   - `vyu.tenant_id` / nested `vyu.tenant_id`, or Cognito-native `custom:vyu_tenant_id`
   - `vyu.workspace_id` / nested `vyu.workspace_id`, or Cognito-native `custom:vyu_workspace_id`
   - role/group claims such as `vyu.roles`, `groups`, `cognito:groups`, or `custom:vyu_roles`
4. Point Vyu at the Cognito JWKS endpoint or discovery document.
5. Keep `VYU_REQUIRE_TENANT_GOVERNANCE=true` so IdP claims are treated as requested access, not final authority.

SAML customers should be federated through Cognito or another OIDC broker. Vyu intentionally validates signed OIDC JWTs at the application boundary instead of implementing direct XML/SAML signature processing inside the service runtime.

## Cognito Provisioning

The checked-in Terraform stack is `deploy/aws/cognito`. It provisions:

- Cognito user pool.
- App client for OAuth authorization-code flow.
- Optional Hosted UI domain.
- Vyu API resource server and scopes.
- Role groups that map to Vyu RBAC.
- Cognito custom attributes for tenant, workspace, and role claims.
- Optional SAML/OIDC enterprise identity providers federated through Cognito.
- A `vyu_operator_env` Terraform output that contains the IdP settings Vyu needs.

Typical flow:

```bash
cd deploy/aws/cognito
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan -out tfplan
terraform apply tfplan
terraform output -json > cognito-outputs.json

python ../../../scripts/render_cognito_operator_env.py \
  --terraform-output-json cognito-outputs.json \
  --tenant-governance-registry /app/config/tenant-governance.json \
  --output deployment.cognito.env
```

Merge the rendered env overlay with the rest of the runtime deployment config.

## Operator Configuration

For AWS Cognito-style production configuration:

```env
VYU_AUTH_MODE=oidc_jwks
VYU_TOKEN_ISSUER=https://cognito-idp.<aws-region>.amazonaws.com/<user-pool-id>
VYU_TOKEN_AUDIENCE=<app-client-id-or-api-audience>
VYU_OIDC_JWKS_URI=https://cognito-idp.<aws-region>.amazonaws.com/<user-pool-id>/.well-known/jwks.json
# or:
# VYU_OIDC_DISCOVERY_URI=https://cognito-idp.<aws-region>.amazonaws.com/<user-pool-id>/.well-known/openid-configuration
VYU_OIDC_ALLOWED_ALGORITHMS=RS256
VYU_OIDC_REQUIRED_TOKEN_USE=id
VYU_OIDC_JWKS_CACHE_TTL_SECONDS=300
VYU_OIDC_FETCH_TIMEOUT_SECONDS=2.0

VYU_TENANT_GOVERNANCE_REGISTRY=/app/config/tenant-governance.json
VYU_REQUIRE_TENANT_GOVERNANCE=true
VYU_REQUIRE_EMAIL_VERIFIED=true
```

Local smoke tests still use `VYU_AUTH_MODE=hs256` because they generate a local test token without calling the cloud IdP. OIDC deployments should be smoke-tested with real IdP-issued JWTs in the AWS environment.

## Runtime Validation

`OidcJwksBearerTokenAuthenticator` validates:

- Authorization bearer scheme
- Three-part JWT structure
- JOSE header JSON
- `alg` allow-list, currently `RS256`
- RSA JWK selection by `kid`
- RS256 signature using the configured JWKS
- trusted `iss`
- accepted `aud`, with Cognito `client_id` fallback for access-token style claims
- required `exp`
- optional `nbf` and `iat` clock checks
- optional Cognito `token_use`

After token validation, Vyu still runs identity mapping and tenant governance. A valid IdP token does not grant access unless the tenant registry has an active tenant, active workspace, active grant, and matching role entitlement.

## JWKS Sources

Vyu can use:

- `VYU_OIDC_JWKS_FILE` for mounted/static JWKS in deterministic test or air-gapped environments.
- `VYU_OIDC_JWKS_URI` for direct JWKS retrieval.
- `VYU_OIDC_DISCOVERY_URI` for OIDC discovery and automatic `jwks_uri` resolution.

Remote JWKS keys are cached by `VYU_OIDC_JWKS_CACHE_TTL_SECONDS`. A failed fetch fails the request closed with `auth_token_invalid`.

## Boundaries

Implemented:

- Application-level external IdP JWT verification.
- AWS/Cognito-compatible JWKS configuration.
- Provider-neutral OIDC validation for enterprise IdPs federated through Cognito/OIDC.
- Deployment composition wiring and fail-closed config validation.
- Tests for RS256 verification, discovery/JWKS caching, token use, Cognito `client_id` fallback, and serverless route enforcement.

Provisioned or supported by this patch:

- Cognito user pool/app client/Hosted UI domain provisioning through Terraform.
- Cognito groups and custom attributes that map cleanly into Vyu identity claims.
- Optional SAML/OIDC enterprise IdP federation through Cognito Terraform resources.
- Operator env rendering from Terraform outputs.

Still not implemented inside the Vyu process:

- Direct SAML XML signature validation.
- SCIM user lifecycle sync.
- MFA and conditional access policy evaluation inside application code.
- Customer-specific Terraform backends, account structure, WAF, Route 53, ACM, ALB/API Gateway, IAM roles, or CI/CD.

Those controls should live in the AWS IdP/IAM/infrastructure layer and feed Vyu signed JWTs plus tenant-governance records.
