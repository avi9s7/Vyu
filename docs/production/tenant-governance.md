# Identity, Access, and Tenant Governance Layer

## Purpose

The tenant governance layer is Vyu's provider-neutral production boundary for deciding who can access a tenant, which workspace they can operate in, which roles they may exercise, which service accounts and API keys are valid, and which tenant-admin lifecycle actions are allowed.

It sits after authentication and before service routing. A deployment may authenticate a human through the configured bearer-token identity provider, or authenticate a non-human integration through a governed API key. In both cases, the mapped identity is checked against Vyu-owned tenant, workspace, membership, service-account, and API-key records before a service route runs.

## Governed Records

The implementation is `src/vyu/authz/tenant_governance.py` and models:

| Record | Purpose |
| --- | --- |
| `TenantRecord` | Tenant ID, display name, lifecycle status, allowed email domains, and metadata. |
| `WorkspaceRecord` | Workspace ID, tenant ownership, lifecycle status, data classification, and metadata. |
| `MembershipGrant` | Human or service-account subject, tenant, workspace or tenant-wide `*` scope, roles, status, access mode, expiry, and grant rationale. |
| `ServiceAccountRecord` | Non-human principal lifecycle, tenant ownership, scopes, and metadata. |
| `ApiKeyRecord` | API-key ID, service-account binding, tenant/workspace scope, role claims, key hash, lifecycle status, expiry, scopes, and rotation metadata. |
| `TenantGovernanceDecision` | Fail-closed entitlement result with effective roles, matched grants, and access modes. |

The registry supports JSON round-tripping through `TenantGovernanceRegistry.read()` and `TenantGovernanceRegistry.write()`. Production composition uses `TenantGovernanceRepository`, a reloadable JSON-backed repository, so admin-route updates can take effect without rebuilding the process.

## Deployment Enforcement

`DeploymentCompositionConfig` now supports:

- `tenant_governance_registry_path`
- `require_tenant_governance`
- `api_key_auth_enabled`
- `api_key_issuer`
- `identity_access_audit_enabled`

When `require_tenant_governance=True`, deployment composition fails closed unless `VYU_TENANT_GOVERNANCE_REGISTRY` points to a valid registry file. When API-key authentication is enabled, the same registry is required because service-account keys are not trusted unless they are bound to active governance records.

The local operator `.env` example points to `config/tenant_governance.local.example.json` and enables tenant governance, API-key auth, and identity access audit by default.

## Enforcement Rules

Identity entitlement is allowed only when all checks pass:

1. The tenant exists and is `active`.
2. The requested workspace exists and is `active`, unless the identity maps to tenant-wide workspace `*`.
3. Human identities satisfy the tenant email-domain allow-list when configured.
4. Service-account identities are active and tenant-bound before bypassing human email-domain checks.
5. At least one active, unexpired membership grant matches the subject, tenant, workspace, and requested role.
6. Tenant-wide grants use workspace `*` and never cross tenant boundaries.
7. Suspended, revoked, expired, or role-mismatched grants are denied.
8. Break-glass grants require a non-empty break-glass reason claim.
9. API keys must hash-match an active key record, bind to an active service account, match tenant ownership, and pass the same membership-grant entitlement checks as human identities.

## Identity Mapping Integration

`IdentityMappingConfig` accepts a `tenant_governance` evaluator. In production deployment composition this is the configured `TenantGovernanceRepository`, not an optional in-memory object.

`IdentityMapper.map_claims()` validates issuer, audience, required identity claims, optional email verification, and external role mapping. It then calls tenant governance to verify the subject is entitled to the tenant/workspace and requested roles.

If a subject claims more roles than their active grants allow, the mapper narrows the effective Vyu role to the highest granted requested role. If no requested role is granted, service routing fails closed with `identity_mapping_failed`.

Mapped service headers remain stable:

- `x-vyu-user-id`
- `x-vyu-tenant-id`
- `x-vyu-workspace-id`
- `x-vyu-role`

Governed metadata is also propagated when available:

- `x-vyu-governed-grant-ids`
- `x-vyu-access-modes`
- `x-vyu-break-glass-reason`

## API Keys and Service Accounts

The deployment HTTP adapter now supports a composite authenticator. If `x-vyu-api-key` is present and API-key auth is enabled, Vyu authenticates through tenant governance. Otherwise it falls back to bearer-token authentication.

API-key records store `sha256:<digest>` hashes, not raw secrets. Admin routes redact key hashes in responses. API-key authentication produces trusted internal claims using `api_key_issuer`, then the normal identity mapper and tenant-governance grant checks run before route dispatch.

## Tenant Admin Lifecycle Routes

`src/vyu/entrypoints/tenant_governance_admin_routes.py` exposes framework-neutral tenant-admin routes under `/v1/admin/...`:

- `GET /v1/admin/tenant-governance`
- `PUT /v1/admin/tenants/{tenant_id}`
- `PUT /v1/admin/workspaces/{workspace_id}`
- `PUT /v1/admin/membership-grants/{grant_id}`
- `POST /v1/admin/membership-grants/{grant_id}/revoke`
- `PUT /v1/admin/service-accounts/{service_account_id}`
- `PUT /v1/admin/api-keys/{key_id}`

These routes require a mapped `tenant_admin` role and use the existing authorization policy before changing governance records.

## Audit Behavior

When `identity_access_audit_enabled=True`, deployment composition writes `identity_access_decision` events to `ProductionStorage` for successful and failed identity mapping decisions. Tenant-admin lifecycle routes emit `tenant_governance_admin_action` events. Audit payloads include request ID, audit correlation ID, route, decision reason, mapped identity metadata, governed grant IDs, access modes, and break-glass use flags.

## Enterprise IdP Integration

AWS-hosted deployments can use `VYU_AUTH_MODE=oidc_jwks` to validate RS256 OIDC bearer JWTs against a JWKS file, JWKS URI, or OIDC discovery document. This is designed for Amazon Cognito user pools and for customer SAML/OIDC providers federated through Cognito or another OIDC broker. See `docs/production/aws-enterprise-idp.md`.

A successful IdP JWT is still only an authenticated claim set. Tenant governance remains the authority for tenant, workspace, grant, service-account, API-key, and break-glass entitlement decisions.

## Current Limits

- The JSON-backed repository is suitable for local/serverless operation and deterministic release evidence; high-volume SaaS operation should move the same schema to transactional database-backed administration.
- Direct SAML XML signature validation, SCIM user lifecycle sync, MFA enforcement, and conditional-access policy evaluation should remain in the enterprise IdP/AWS infrastructure layer and feed Vyu signed OIDC JWTs plus governance records.
- Break-glass now fails closed and audits use, but enterprise notification and post-use review workflows should be added when the human-review layer owns review escalations.
