# Product Claim Inventory

## Purpose

This inventory keeps approved Vyu claims aligned with the intended-use policy and current implementation state. It is a production control: claims made in the UI, API docs, reports, sales material, and demos must stay within this inventory until reviewed.

## Allowed Claims

| Claim | Current Basis | Conditions |
| --- | --- | --- |
| Vyu supports governed biomedical literature research workflows. | Deterministic Phase 0-7 POC and production foundation docs. | Limited to approved sources and qualified users. |
| Vyu can generate citation-grounded summaries over controlled evidence contexts. | Phase 4 grounded answer contracts and citation validation. | Claims must cite existing passage identifiers. |
| Vyu surfaces automated evidence quality signals and governance warnings. | Phase 5 evidence profile, Trust Score, and Governance Box outputs. | Must be described as automated POC signals, not formal clinical grading. |
| Vyu can produce auditable local run artifacts. | Phase-output runner, artifact manifest, run summary, and SQLite audit storage. | Current implementation is local and deterministic. |
| Vyu enforces source approval gates for production-shaped connector usage. | Source registry and `SourceApprovalTransport`. | Source records must be approved for the intended use. |
| Vyu supports tenant/workspace scoped production-shaped storage reads. | `ProductionStorage` scoped manifest and audit event methods. | Not a substitute for full production IAM. |

## Restricted Claims

| Claim | Required Before Use |
| --- | --- |
| Clinically validated decision support. | Regulatory, clinical safety, validation, and legal approval. |
| HIPAA-ready PHI/ePHI processing. | Privacy/security architecture, BAA readiness, encryption, access control, audit, and incident response approval. |
| Fully automated formal evidence grading. | Approved evidence methodology, expert validation, and human-review workflow. |
| Production-grade multi-tenant SaaS. | Authentication, authorization, deployment, monitoring, backup, incident response, and security review. |
| Live literature coverage is complete or current. | Connector freshness metrics, source monitoring, and index-version evidence. |

## Owner Review

Product owns this inventory. Legal/regulatory, clinical safety, privacy, and security owners must review any new claim before it is used externally.
