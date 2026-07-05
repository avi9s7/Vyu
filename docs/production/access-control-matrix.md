# Access Control Matrix

## Purpose

This matrix defines the first production-shaped authorization rules for Vyu. It is a local policy baseline for tenant/workspace authorization and does not replace production identity, SSO, MFA, or centralized IAM.

## Scope Model

Every authorization decision is evaluated against:

- `tenant_id`
- `workspace_id`
- user membership
- role assignment
- requested action

Workspace membership applies only to the exact tenant and workspace unless the workspace is `*`, which is reserved for tenant-wide administration within the same tenant.

## Role Permission Matrix

| Role | Scope | Allowed actions |
| --- | --- | --- |
| `researcher` | Assigned workspace | Read artifacts, read audit events, run research |
| `reviewer` | Assigned workspace | Researcher actions, review outputs, export reports |
| `workspace_admin` | Assigned workspace | Reviewer actions, manage workspace |
| `tenant_admin` | Tenant-wide workspace `*` | All production authorization actions within the same tenant |

## Actions

| Action | Meaning |
| --- | --- |
| `read_artifact` | Read generated artifacts and manifests in scope |
| `read_audit_event` | Read audit events in scope |
| `run_research` | Start a research workflow in scope |
| `review_output` | Review, approve, or reject a high-risk output |
| `export_report` | Export a report after required review gates |
| `manage_sources` | Manage source registry records for the tenant |
| `manage_workspace` | Manage workspace settings and membership |

## Enforcement Rules

- A user with no matching tenant/workspace membership is denied.
- A user with matching scope but no role permission for the action is denied.
- Tenant admins can act across workspaces only inside their own tenant.
- Cross-tenant access is always denied.
- Denied checks raise `PermissionError` when callers use `AuthorizationPolicy.require`.

## Implementation

The local policy implementation is `src/vyu/authz/`. It is intentionally dependency-free so future API, storage, review, and export code can call the same role rules before production IAM is introduced.


## Tenant Governance Layer

`src/vyu/authz/tenant_governance.py` adds governed tenant records, workspace records, membership grants, service accounts, API keys, and tenant-admin lifecycle controls above the role matrix. The authorization matrix still decides whether a role can perform an action, while the tenant governance registry decides whether the authenticated identity is entitled to the tenant/workspace and role it claims.

Tenant governance denies suspended tenants, suspended or archived workspaces, revoked/suspended/expired grants, email domains outside a configured tenant allow-list for human identities, ungranted role escalation, inactive service accounts/API keys, expired API keys, and break-glass grants without a trusted reason claim.
