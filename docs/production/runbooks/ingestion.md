# Evidence ingestion operator runbook

Operator runbook for governed non-PHI document upload, quarantine screening, parsing, promotion, evidence library access, reprocessing, and retention escalation in VYU AWS environments (`dev`, `staging`, `prod`).

## Scope

This runbook covers:

- Stuck upload and checksum mismatch triage
- Malware and suspected PHI blocks
- Parser failures and unsupported formats
- Exact duplicates and wrong metadata
- Quarantine retention and safe security-review download
- Governed reprocess requests
- Soft-delete retention requests and physical deletion escalation
- Dashboard and alarm interpretation

It complements:

- `POST /v1/uploads/presign` and finalize flow
- `GET /v1/evidence-documents*` and `GET /v1/ingestion-jobs/{job_id}`
- `POST /v1/evidence-documents/{id}/reprocess`
- `POST /v1/evidence-documents/{id}/retention-request`
- `scripts/reprocess_document.py`
- CloudWatch dashboard `vyu-{env}-operations`

## Prerequisites

Before any write action, record:

| Field | Example |
| --- | --- |
| Operator | `jane.doe@company.invalid` |
| UTC timestamp | `2026-07-07T16:00:00Z` |
| Environment | `staging` |
| Tenant ID | UUID |
| Workspace ID | UUID |
| Document ID | UUID |
| Ticket / change record | Internal reference |

Required access:

- Workspace admin bearer token for reprocess and retention actions
- Read access to evidence library APIs for triage
- AWS read access to quarantine bucket objects for security review only
- CloudWatch dashboard and alarm subscription for `vyu-{env}-*`

Never paste bearer tokens, object keys, scanner match text, or document body into tickets or chat.

## 1. Inspect document and job status

1. List recent documents:

```powershell
curl -sS -H "Authorization: Bearer $env:VYU_OPERATOR_BEARER_TOKEN" `
  "https://api.staging.example.com/v1/evidence-documents?status=blocked&limit=20"
```

2. Fetch document detail:

```powershell
curl -sS -H "Authorization: Bearer $env:VYU_OPERATOR_BEARER_TOKEN" `
  "https://api.staging.example.com/v1/evidence-documents/{document_id}"
```

3. Fetch ingestion job events:

```powershell
curl -sS -H "Authorization: Bearer $env:VYU_OPERATOR_BEARER_TOKEN" `
  "https://api.staging.example.com/v1/ingestion-jobs/{job_id}"
```

API responses are sanitized. They do not include quarantine keys, scanner-sensitive matches, or full parsed document bodies.

Use `block_summary.code` for blocked documents. Common terminal codes:

| Code | Meaning | Retrieval available |
| --- | --- | --- |
| `checksum_mismatch` | Uploaded object does not match declared SHA-256 | No |
| `object_missing` | Object never arrived or was removed before verify | No |
| `malware_infected` | Malware rules flagged the object | No |
| `phi_suspected_phi` | Sensitive-data rules flagged suspected PHI | No |
| `phi_unknown` | Classifier could not confidently clear PHI risk | No |
| `parser_unsupported_format` | Media type or extension is not supported | No |
| `parser_malformed_document` | Supported format could not be parsed safely | No |
| `duplicate_exact` | Workspace duplicate reused canonical ready version | Yes (canonical version) |
| `ready` | Promoted to evidence storage with chunks | Yes |

## 2. Stuck upload (`awaiting_upload`)

Symptoms:

- Document remains `awaiting_upload` after the browser finished uploading
- Finalize was never called or failed before verify

Steps:

1. Confirm presign expiry (`expires_at` from the original upload response or audit event `upload_presign_issued`).
2. Ask the uploader to retry with a fresh presign if the POST URL expired.
3. If the object exists in quarantine but finalize was missed, have the client call finalize for the same `document_id` and `version_id`.
4. If the object is missing, issue a new upload. Do not mutate database rows directly.

Abort if the document is already `uploaded`, `scanning`, or beyond; use the ingestion job timeline instead.

## 3. Checksum mismatch

Symptoms:

- Terminal code `checksum_mismatch`
- Status `blocked` or `failed`

Steps:

1. Confirm the client declared SHA-256 at presign time matches the file actually uploaded.
2. Check for proxy or multipart corruption during direct browser upload.
3. Request a clean re-upload with a new version. Do not copy quarantine objects into evidence storage manually.
4. Record the incident if repeated for the same source or tenant.

## 4. Malware block

Symptoms:

- Terminal code `malware_infected` or `malware_suspicious`
- Alarm `vyu-{env}-ingestion-malware-infected` in `ALARM`

Steps:

1. Leave the object in quarantine. Never promote it to evidence storage.
2. Use document detail and job events only for triage. Do not export scanner match text into tickets.
3. For security review, download from quarantine through the approved break-glass S3 path with object-level logging enabled. Access must be time-bound and ticketed.
4. If the file is a known test artifact (for example EICAR in a controlled exercise), document the exercise and close the ticket. Do not disable scanners in production.
5. Escalate repeated infections from the same tenant/workspace to security operations.

## 5. Suspected PHI or unknown classification

Symptoms:

- Terminal code `phi_suspected_phi` or `phi_unknown`
- Alarms `vyu-{env}-ingestion-phi-blocked` or `vyu-{env}-ingestion-phi-unknown`

Steps:

1. Treat the upload as PHI-risk and keep it quarantined.
2. Confirm the source registry entry requires `contains_phi=false` at presign.
3. Review filename, media type, and source policy with the workspace owner.
4. Do not send quarantined content to models or retrieval.
5. If business owners assert the file is non-PHI, route through privacy review before any reprocess attempt. Reprocessing does not bypass screening.

## 6. Parser crash or unsupported format

Symptoms:

- Terminal code `parser_unsupported_format`, `parser_malformed_document`, or `parser_timeout`
- Alarm `vyu-{env}-ingestion-parser-failures`

Steps:

1. Confirm the file type is in the approved supported list (PDF, DOCX, TXT, HTML for pilot).
2. Inspect `parser_name` / `parser_version` on the version summary when available.
3. If the format is newly approved, use governed reprocess after deploying the parser version that supports it.
4. If the file is damaged, request a clean export from the source system and re-upload.
5. For isolated parser worker crashes, check worker logs and ECS task restarts. Parser failures must remain blocked until a successful verify completes.

## 7. Exact duplicate

Symptoms:

- Terminal code `duplicate_exact`
- Status `ready`
- New version metadata references `duplicate_of_version_id`

Steps:

1. Confirm this is expected when the same workspace uploads the same SHA-256 twice.
2. Use the canonical ready version for retrieval and citations.
3. No operator action is required unless the duplicate indicates a faulty client loop. In that case coordinate with the application owner.
4. Monitor `IngestionDuplicates` on the operations dashboard for abnormal spikes.

## 8. Wrong metadata (title, source, external ID)

Symptoms:

- Document reached `ready` but bibliographic metadata is wrong
- Source or `external_id` does not match the upstream system

Steps:

1. Metadata corrections that do not require re-parsing may be handled by a new governed upload with the correct `external_id` if the product policy allows version increments.
2. If parser output or chunk boundaries must change, use reprocess (section 10).
3. Never edit `documents` or `document_versions` rows directly in production.

## 9. Quarantine retention and age

Symptoms:

- Blocked objects remain in quarantine for a long time
- Alarm `vyu-{env}-ingestion-quarantine-age` in `ALARM`

Steps:

1. Review blocked documents older than seven days.
2. Confirm no legal hold or open security investigation applies.
3. Soft-delete requests use `POST /v1/evidence-documents/{id}/retention-request` and mark the document `deleted` in the library API.
4. Physical deletion of quarantine and evidence objects is a separate authorized retention job. It must preserve audit and legal-hold state.
5. Do not delete quarantine objects manually unless executing an approved retention workflow with evidence capture.

## 10. Governed reprocess

Use API credentials only. Production reprocess must not write database tables directly.

Dry-run:

```powershell
$env:VYU_REPROCESS_BEARER_TOKEN = "<workspace-admin-token>"
uv run python scripts/reprocess_document.py `
  --environment staging `
  --base-url https://api.staging.example.com `
  --tenant-id "{tenant_id}" `
  --workspace-id "{workspace_id}" `
  --document-id "{document_id}" `
  --version-id "{optional_source_version_id}" `
  --reason "Reparse after parser 1.0.1 deployment" `
  --actor "jane.doe@company.invalid" `
  --target-parser-version "1.0.1" `
  --target-chunker-version "1.0.0" `
  --mode dry-run
```

Apply:

```powershell
uv run python scripts/reprocess_document.py `
  --environment staging `
  --base-url https://api.staging.example.com `
  --tenant-id "{tenant_id}" `
  --workspace-id "{workspace_id}" `
  --document-id "{document_id}" `
  --reason "Reparse after parser 1.0.1 deployment" `
  --actor "jane.doe@company.invalid" `
  --target-parser-version "1.0.1" `
  --target-chunker-version "1.0.0" `
  --mode apply
```

Rules:

- Caller must be a workspace admin (`MANAGE_WORKSPACE`).
- `Idempotency-Key` is required; the script generates a deterministic key when omitted.
- Reprocess creates a new `document_version` and `ingestion.verify` job. It does not mutate an approved ready version in place.
- Poll `GET /v1/ingestion-jobs/{job_id}` until terminal `ready` or a blocked code appears.

## 11. Deletion escalation

Soft delete (library state only):

```powershell
curl -sS -X POST `
  -H "Authorization: Bearer $env:VYU_OPERATOR_BEARER_TOKEN" `
  -H "Content-Type: application/json" `
  -d '{"reason":"Workspace offboarding per ticket INC-1234."}' `
  "https://api.staging.example.com/v1/evidence-documents/{document_id}/retention-request"
```

Escalation path:

1. Workspace admin submits retention request with reason.
2. Privacy / security reviews open investigations and legal hold.
3. Authorized retention job removes quarantine and evidence objects after hold clearance.
4. Audit events and ingestion history remain per policy.

## 12. Dashboards and alarms

Primary dashboard: `vyu-{env}-operations`

| Signal | Metric / source | Action |
| --- | --- | --- |
| Upload volume | `IngestionUploads`, `IngestionBytes` | Capacity review |
| Scan latency | `IngestionScanLatencyMs` p95 | Worker scaling / scanner health |
| Scan errors | `IngestionScanErrors` | Inspect blocked job events |
| Malware | `IngestionMalwareInfected` | Section 4 |
| PHI blocked | `IngestionPhiBlocked` | Section 5 |
| PHI unknown | `IngestionPhiUnknown` | Section 5 |
| Parser failures | `IngestionParserFailures` | Section 6 |
| Queue age | `ApproximateAgeOfOldestMessage` on ingestion queue | Scale workers / inspect DLQ |
| Ready latency | `IngestionReadyLatencyMs` p95 | End-to-end pipeline review |
| Duplicates | `IngestionDuplicates` | Section 7 |
| Quarantine age | `IngestionQuarantineAgeSeconds` p95 | Section 9 |

Related infrastructure alarms already in place:

- `vyu-{env}-jobs-depth` and `vyu-{env}-jobs-oldest-age`
- `vyu-{env}-jobs-dlq-messages`
- `vyu-{env}-job-failures`

## 13. Staging validation exercise

Run after promoting ingestion changes to `staging` and before marking Plan 5 complete.

```powershell
$env:VYU_INGESTION_STAGING_BEARER_TOKEN = "<researcher-or-uploader-token>"
uv run python scripts/validate_ingestion_staging.py `
  --environment staging `
  --base-url https://api.staging.example.com `
  --output evidence/plan5-staging-validation.json
```

The validator exercises:

- Clean TXT/PDF/DOCX/HTML uploads through presign → S3 POST → finalize → job poll → `ready` with chunks
- EICAR and synthetic PHI fixtures remain blocked and non-retrievable
- Duplicate finalize idempotency and duplicate content reuse
- Presign KMS, checksum metadata, and expiry binding

Record the JSON output using `docs/production/evidence/plan5-staging-validation.template.json` as the evidence shell. Confirm ingestion alarms on `vyu-staging-operations` are not in sustained `ALARM` during the exercise.

CI integration coverage without live AWS lives in `tests/integration/ingestion/test_staging_validation.py`.

## 14. Abort conditions

Stop and escalate when:

- A blocked object is requested for retrieval or model use
- Scanner bypass is requested in production
- Direct database or S3 evidence mutation is proposed instead of API/workflow
- Cross-tenant document access is observed
- Reprocess is requested without workspace admin authorization
- Physical deletion is requested while legal hold may apply

## Evidence template

```text
Environment:
Operator:
UTC start / end:
Tenant ID:
Workspace ID:
Document ID:
Version ID:
Job ID:
Symptom:
Terminal code:
Action taken:
API request IDs:
Alarm state before / after:
Outcome:
Follow-up owner:
```
