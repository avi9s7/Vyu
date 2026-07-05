# Privacy Data Flow and PHI/ePHI Gate

## Purpose

This document defines the first privacy data-flow baseline for Vyu. The current product scope remains public or approved licensed literature research. Patient-specific context, PHI, and ePHI remain blocked unless privacy, security, regulatory, and clinical safety approvals are present.

## Data Flow

```text
source registry
  -> privacy classification
  -> PHI/ePHI gate
  -> connector/retrieval/model/review workflow
  -> scoped storage and audit events
  -> reviewed export
```

The gate is implemented in `src/vyu/privacy/`.
Gate decisions and completed approval evidence can be persisted as scoped SQLite records through `src/vyu/storage/production.py` for operator inspection and backup/restore.
Framework-neutral API and worker adapters live in `src/vyu/entrypoints/privacy_approval.py` and call the same gate without introducing a web framework or queue dependency.

## Data Classes

| Data class | Examples | Default handling |
| --- | --- | --- |
| `public_literature` | PubMed metadata, synthetic fixtures | Allowed when source governance approves use |
| `licensed_content` | Subscription literature, licensed corpora | Requires source terms and access policy |
| `customer_document` | Uploaded evidence review or internal PDF | Requires tenant/workspace isolation and retention policy |
| `pii` | Direct identifiers outside healthcare context | Requires privacy review before production use |
| `phi` | Patient notes, claims, encounters, lab values | Blocked unless privacy and security approval exist |
| `ephi` | Electronic PHI in production systems | Blocked unless privacy and security approval exist |

## PHI/ePHI Gate

The gate evaluates:

- workflow purpose
- data classification
- source `source_type`
- source `phi_pii_status`
- source allowed and forbidden uses
- approval records

The gate blocks by default when:

- PHI/ePHI is present without `privacy` and `security` approvals
- a patient-specific recommendation is requested without `regulatory` and `clinical_safety` approvals
- PHI/ePHI would be sent to a model provider without `model_provider` approval
- a source forbids the requested purpose
- a source does not list the requested purpose in `allowed_uses`

## Required Approvals

| Scenario | Required approvals |
| --- | --- |
| PHI/ePHI handling | `privacy`, `security` |
| Patient-specific recommendation | `regulatory`, `clinical_safety` |
| PHI/ePHI sent to model provider | `privacy`, `security`, `model_provider` |
| Patient-specific recommendation using PHI/ePHI | `privacy`, `security`, `regulatory`, `clinical_safety` |

## Persistence and Inspection

Privacy approval records capture:

- tenant and workspace scope
- run ID and approval ID
- workflow purpose and data classification
- gate decision status and allow/block result
- decision reasons and missing approvals
- completed approval evidence
- creation time

Records are stored in the production SQLite adapter, emit `privacy_approval_recorded` audit events, appear in `scripts/inspect_production_store.py` output under `privacy_approval_records`, and are included in production backup/restore payloads.

The workflow adapters accept tenant/workspace scope, run ID, purpose, data classification, source records, and approval evidence. They return a serializable allow/block decision and can persist the same decision for audit and operator inspection when called with a production storage adapter.

## Current Limitations

- The gate is a local policy object, not a production DLP scanner.
- The gate does not identify PHI from raw free text.
- There is no deployed production privacy approval route or reviewer UI.
- Field-level encryption, retention jobs, deletion workflows, and BAA readiness are not implemented.
