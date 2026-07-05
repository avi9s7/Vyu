# Production Threat Model

## Scope

This threat model covers the planned production Vyu workflow: live connectors, retrieval indexes, model gateway, governance outputs, human review, persisted artifacts, and audit logs.

## Assets

- Source registry and source credentials.
- Literature corpus snapshots and indexes.
- Customer documents and reports.
- Generated answers, citations, governance records, and review decisions.
- Model prompts, configurations, and evaluation data.
- Audit/event logs.
- Tenant, workspace, user, and role records.

## Trust Boundaries

- User/browser to API gateway.
- API gateway to application services.
- Application services to workers.
- Workers to external connectors.
- Workers to model providers.
- Services to databases, object storage, indexes, and audit logs.
- Human reviewers to exportable reports.

## Threats

| Threat | Example | Required Mitigation |
| --- | --- | --- |
| Cross-tenant data access | User retrieves another tenant's report | Tenant-scoped authorization and query filters |
| Prompt injection | Retrieved source text instructs model to ignore policy | Prompt isolation, source labeling, output validation |
| Citation fabrication | Model cites nonexistent evidence | Citation validator and export blocking |
| Source poisoning | Bad or manipulated source enters index | Source approval, provenance, quarantine, review |
| Credential leakage | Connector API key appears in logs | Secret store, log redaction, scans |
| PHI leakage | Patient data sent to unapproved model provider | PHI gate, provider policy, DLP checks |
| Overreliance | User treats summary as medical advice | Intended-use warnings and human review gates |
| Audit tampering | Governance records are modified after export | Append-only event store and checksums |
| Stale evidence | Old index omits important updates | Source freshness metrics and index versioning |
| Denial of service | Connector or model calls saturate system | Rate limits, circuit breakers, queues |

## Initial Controls

- Environment-scoped runtime settings.
- Connector retry and rate-limit policy.
- PubMed HTTP and replay transports with gated live-test coverage.
- Connector source approval gate for approved intended uses.
- PHI/ePHI gate for patient data, patient-specific recommendations, and model-provider calls.
- Privacy approval persistence and audit events for PHI/ePHI gate decisions.
- Framework-neutral privacy approval API and worker adapters for PHI/ePHI gate decisions.
- Prompt-injection scan and citation-policy export gate before future model gateway use.
- Prompt-injection and citation-policy decision audit events when report export is called with production storage.
- Artifact manifests with source and index metadata.
- Evaluation registry for benchmark and release-gate evidence.
- SQLite production audit event storage for artifact and evaluation persistence events.
- tenant/workspace scoped storage reads for artifact manifests and audit events.
- Production readiness checks for source metadata, checksums, scope rejection, evaluation evidence, connector evidence, approved review state, report-export audit evidence, and audit events.
- Backup export and restore commands for local production-shaped recovery drills.
- Production docs defining intended use, source registry, and security controls.

## Open Risks

- Production IAM is not yet implemented.
- Live connector staging validation beyond the gated PubMed smoke test is not yet complete.
- Persistent audit/event storage is local SQLite only, not a hardened immutable production event store.
- Human review workflow, persisted queue service boundaries, framework-neutral queue adapters, and the reviewer queue route runtime exist locally, but no reviewer UI, web server, auth middleware, or deployed worker queue exists.
- Model gateway is not yet implemented.
- Prompt-injection scan is deterministic pattern matching, not a full adversarial classifier.
- PHI/ePHI detection is policy-driven; production DLP scanning, deployed privacy approval routes, and reviewer UI are not implemented.
- Production deployment, monitoring, encryption, and incident-response automation are not yet implemented.
