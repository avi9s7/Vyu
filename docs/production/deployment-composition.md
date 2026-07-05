# Deployment Composition

Deployment composition builds the local/serverless runtime graph for deployment-shaped testing without adding cloud infrastructure.

The implementation is `src/vyu/deployment/composition.py`. It accepts explicit `DeploymentCompositionConfig`, creates production storage, review/report/admin route runtimes, identity mapping, bearer/API-key authentication, deployment HTTP adapter, API service shell, and serverless handler objects.

## Composition Contract

`DeploymentCompositionConfig` requires:

- SQLite database path
- phase-output artifact directory
- token issuer
- token audience
- HS256 secret when `auth_mode=hs256`

It also supports local options for unauthenticated paths, request ID prefix, token leeway, email-verification requirement, serverless response headers, identity-access audit, tenant-governance registry path, fail-closed tenant-governance enforcement, API-key auth, API-key issuer, and `auth_mode=oidc_jwks` with JWKS/discovery settings for AWS enterprise IdP validation.

`build_deployment_runtime(...)` returns a `DeploymentRuntimeBundle` containing the composed runtime objects, including the optional `TenantGovernanceRepository` and tenant-admin route runtime when a registry path is configured.

## Tenant Governance Operation

When `require_tenant_governance=True`, composition fails closed unless the configured registry file exists and can be parsed. When `api_key_auth_enabled=True`, the same registry is mandatory because API-key authentication is backed by governed service-account and API-key records.

When `identity_access_audit_enabled=True`, successful and failed identity mapping decisions are appended to `ProductionStorage` as `identity_access_decision` events. Tenant-admin lifecycle operations emit `tenant_governance_admin_action` events through the same audit sink.

## Current Limits

- This is local/serverless composition only.
- It does not create infrastructure, IAM, rate limits, WAF, Cognito user pools, or IdP federation resources.
- It validates OIDC/JWKS tokens when configured, but provider setup, MFA, conditional access, and SCIM are AWS/IdP responsibilities.
- It still uses the current local phase-output artifact store for report export.
