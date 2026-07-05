# Security Architecture

## Scope

This document defines the first production security architecture for Vyu. It focuses on tenant isolation, access control, auditability, data protection, and secure operation of live connectors and AI-assisted workflows.

## Security Controls

| Control Area | Required Control |
| --- | --- |
| Identity | SSO/OIDC or SAML, MFA for privileged users, service identities for workers |
| Authorization | RBAC or ABAC over tenants, workspaces, projects, sources, reports, and admin actions |
| Tenant isolation | Tenant/workspace identifiers on every persisted object and query boundary |
| Network security | TLS for all service communication and egress restrictions for connectors |
| Secrets | Managed secret store, no secrets in source, logs, manifests, or artifacts |
| Encryption | Encryption at rest for databases, object storage, indexes, backups, and audit logs |
| Audit | Append-only logging for user access, source access, retrieval, generation, review, export, and admin changes |
| Vulnerability management | Dependency scanning, secret scanning, container scanning, and SBOM generation |
| Incident response | Runbooks for security incidents, privacy incidents, bad outputs, and connector compromise |
| Data lifecycle | Retention, deletion, legal hold, and source retirement workflows |

## Production Boundaries

```text
client -> API gateway -> application service -> workflow workers
                                      |-> connector gateway
                                      |-> retrieval/model/governance services
                                      |-> audit/event store
```

Every boundary must enforce authentication, authorization, request validation, and audit logging.

## Minimum Production Requirements

- No anonymous production access.
- No cross-tenant queries.
- All API, storage, review, and export paths must call authorization checks before returning scoped data.
- High-risk report export paths must call the human review export gate before releasing output.
- No live connector credentials in local files.
- No PHI/ePHI handling until the PHI/ePHI gate confirms privacy and security controls are approved.
- No high-risk output export without required review state.
- Report export paths call authorization, human review, prompt-injection, and citation-policy gates before releasing output.
- No production deployment without backup, restore, monitoring, and incident response.

## Security Evidence

Production releases should retain evidence for:

- Threat model review.
- Access control tests.
- Dependency and container scans.
- Secret scans.
- Audit log completeness tests.
- Backup/restore drills.
- Incident response tabletop exercises.
