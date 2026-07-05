# Claim Mapping Contract

The identity mapping module converts trusted deployed identity claims into Vyu service headers.

The implementation is `src/vyu/authn/identity.py`. It deliberately does not verify raw tokens, call an identity provider, or choose SSO/OIDC/SAML. A deployment adapter must authenticate the request first, then pass trusted claims into this mapper.

## Mapping Inputs

`IdentityMappingConfig` defines:

- trusted issuers
- accepted audiences
- user ID claim path
- tenant ID claim path
- workspace ID claim path
- role claim paths
- role mappings from external values into Vyu `Role`
- optional email-verification requirement
- tenant governance evaluator for entitlement checks when deployed with governance enforcement
- optional break-glass reason claim path

Claim paths may be flat keys such as `vyu.tenant_id` or nested paths such as `org.tenant`.

## Output Headers

Successful mappings produce these service headers:

- `x-vyu-user-id`
- `x-vyu-tenant-id`
- `x-vyu-workspace-id`
- `x-vyu-role`

When tenant governance provides grant metadata, mappings can also emit `x-vyu-governed-grant-ids`, `x-vyu-access-modes`, and `x-vyu-break-glass-reason`.

When `ServiceRouteRuntime` is configured with an `IdentityMapper`, trusted mapped claims overwrite any client-supplied identity headers before route dispatch.

## Fail-Closed Behavior

Mapping fails when:

- issuer is not trusted
- audience is missing or not accepted
- required user, tenant, or workspace claims are missing
- email verification is required but not present
- no trusted role claim maps to a Vyu role

Service routes return `identity_mapping_failed` before dispatch when trusted claims cannot be mapped.

## Current Limits

- Token verification is outside this identity-mapping module, but deployment composition can now enforce OIDC/JWKS token validation through `VYU_AUTH_MODE=oidc_jwks`.
- Group-to-role mappings are static configuration.
- Direct SAML XML processing, MFA, conditional access, and SCIM sync remain identity-provider/AWS infrastructure responsibilities.


## Tenant Governance Integration

`IdentityMappingConfig.tenant_governance` can be set to a `TenantGovernanceRegistry` or reloadable `TenantGovernanceRepository`. When present, mapped external roles are treated as requested roles only. The registry must confirm the tenant, workspace, user membership, grant status, expiry, email-domain policy, and access mode before the mapper emits service headers.

If the external identity claims a higher role than the active grant allows, the mapper narrows the output `x-vyu-role` to the highest granted requested role. If no requested role is granted, mapping fails closed with `identity_mapping_failed`. Break-glass grants require a non-empty claim at `IdentityMappingConfig.break_glass_reason_claim`.
