# VYU Evidence Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add governed non-PHI document upload, quarantine, scanning, parsing, deduplication, versioning, chunking, provenance, and status APIs backed by S3 and PostgreSQL.

**Architecture:** Browsers upload directly to a tenant-scoped quarantine key through a short-lived presigned POST. An ingestion job verifies the object, scans malware and sensitive-data risk, validates source policy, normalizes supported formats, writes immutable evidence objects/chunks, and promotes approved binaries to the evidence bucket. Failed or uncertain files remain quarantined and cannot be retrieved or sent to a model.

**Tech Stack:** FastAPI, PostgreSQL, Alembic, S3, SQS ingestion queue, Boto3, libmagic/python-magic, pypdf, python-docx, BeautifulSoup, ClamAV scanner adapter, deterministic sensitive-data rules, pytest.

---

## Entry Gate

- Plans 1-4 are complete.
- Staging API/worker/S3/SQS/RDS deployment and rollback pass.
- Non-PHI upload policy and supported file list are approved.

## Planned File Map

```text
src/vyu/ingestion/
  contracts.py
  service.py
  object_store.py
  classifiers.py
  malware.py
  parsers/
    base.py
    pdf.py
    docx.py
    text.py
    html.py
  chunking.py
  repository.py
src/vyu/api/routers/uploads.py
src/vyu/api/routers/evidence_documents.py
src/vyu/migrations/versions/0004_evidence_ingestion.py
scripts/reprocess_document.py
tests/unit/ingestion/
tests/integration/ingestion/
tests/api/test_ingestion_routes.py
```

## Task 1: Define the Ingestion Schema and State Machine

**Files:** models, migration `0004`, migration/state tests

- [ ] Add tables:

```text
documents(id, tenant_id, workspace_id, source_id, external_id, title,
          status, current_version_id, created_by, created_at, updated_at)
document_versions(id, tenant_id, workspace_id, document_id, version,
                  original_bucket, original_key, original_version_id,
                  normalized_bucket, normalized_key, normalized_version_id,
                  sha256, size_bytes, media_type, filename, classification,
                  malware_status, phi_status, parser_name, parser_version,
                  page_count, metadata, created_at)
evidence_objects(id, tenant_id, workspace_id, document_version_id,
                 object_type, bucket, key, version_id, sha256, media_type,
                 metadata, created_at)
document_chunks(id, tenant_id, workspace_id, document_version_id,
                ordinal, citation_id, text, text_sha256, token_count,
                page_from, page_to, section, metadata, created_at)
ingestion_events(id, tenant_id, workspace_id, document_id, job_id,
                 sequence, status, code, safe_message, details, created_at)
```

- [ ] Enforce unique document `(tenant_id, workspace_id, source_id, external_id)` when external ID exists, unique version `(document_id, version)`, unique chunk `(document_version_id, ordinal)`, and unique citation ID per version.

- [ ] States: `awaiting_upload`, `uploaded`, `scanning`, `blocked`, `parsing`, `chunking`, `ready`, `failed`, `deleted`. Only `ready` versions are queryable by retrieval.

- [ ] Enable/force exact tenant/workspace RLS. Write upgrade/downgrade/re-upgrade tests and illegal-transition tests.

- [ ] Verify and commit:

```powershell
uv run alembic upgrade head
uv run pytest tests/integration/ingestion/test_migration.py tests/unit/ingestion/test_state_machine.py -q
git add src/vyu/ingestion src/vyu/migrations/versions/0004_evidence_ingestion.py tests
git commit -m "feat: add governed evidence ingestion schema"
```

## Task 2: Implement Tenant-Safe Presigned Uploads

**Files:** `object_store.py`, `routers/uploads.py`, API/S3 adapter tests

- [ ] `POST /v1/uploads/presign` accepts filename, declared media type, size, SHA-256, source ID, and explicit `contains_phi=false` attestation.

- [ ] Reject missing/true PHI attestation, unsupported extension/media pair, double extension, control characters, size over 50 MiB, unapproved `internal_documents` source policy, and actors without upload permission.

- [ ] Generate server-owned key:

```text
{env}/{tenant_id}/{workspace_id}/quarantine/{document_id}/{version_id}/{sanitized_filename}
```

- [ ] Presigned POST expires in 10 minutes and requires exact key, content-length range, approved content type, KMS encryption, SHA-256 metadata, tenant/workspace/document/version metadata, and no public ACL.

- [ ] Create document/version/job/outbox/audit records transactionally before returning upload fields. Never trust an object key supplied by the browser.

- [ ] Tests decode POST conditions and prove wrong tenant/key/type/size/encryption cannot satisfy them; cross-tenant document lookup returns `404`.

- [ ] Commit after API contract and LocalStack upload integration tests pass.

## Task 3: Verify Object Integrity Before Processing

**Files:** `service.py`, `object_store.py`, `tests/integration/ingestion/test_object_verification.py`

- [ ] Worker handles `ingestion.verify` only after an explicit finalize request or S3 event matched to the database version.

- [ ] HEAD the object and require exact bucket/key, nonzero size, expected size, KMS encryption, metadata scope IDs, content type, and checksum. Stream SHA-256 when provider checksum metadata is absent; never load the whole file into memory.

- [ ] Mark mismatch `blocked` with safe code (`size_mismatch`, `checksum_mismatch`, `scope_metadata_mismatch`, `encryption_missing`, `object_missing`) and append audit/event records. Do not delete evidence automatically.

- [ ] Duplicate finalize/events reuse the same job/version and do not repeat scans once a terminal scan result exists.

- [ ] Test valid object, missing object, metadata spoof, checksum mismatch, duplicate event, and 50 MiB streaming behavior.

## Task 4: Add Malware and Sensitive-Data Screening

**Files:** `malware.py`, `classifiers.py`, scanner fixture corpus, unit/integration tests

- [ ] Define protocols:

```python
class MalwareScanner(Protocol):
    def scan(self, stream: BinaryIO, *, filename: str) -> MalwareResult: ...

class SensitiveDataClassifier(Protocol):
    def classify(self, text_sample: str, metadata: Mapping[str, str]) -> ClassificationResult: ...
```

- [ ] Malware results are `clean`, `infected`, `error`, or `unknown`. Only `clean` proceeds. Use a pinned scanner image/definitions policy; EICAR fixture must be detected in CI without storing live malware.

- [ ] Sensitive-data results are `non_phi`, `suspected_phi`, or `unknown`. Detect common patient identifiers, medical-record labels/numbers, dates tied to patient labels, contact identifiers, and explicit clinical-note structure. `suspected_phi` and `unknown` remain blocked for manual security/privacy review.

- [ ] Scan a bounded text extraction/sample locally; do not send quarantine content to an external model or API.

- [ ] Record scanner/classifier name, version, definition timestamp, safe finding categories, and content hash. Do not persist matched sensitive values.

- [ ] Tests cover clean PDF, EICAR, scanner timeout, empty/unsupported file, synthetic patient identifiers, public article false-positive fixtures, and classifier uncertainty.

## Task 5: Parse Supported Formats Safely

**Files:** parser modules and parser contract tests

- [ ] Support PDF, DOCX, UTF-8 TXT, and sanitized HTML for the first release. Reject encrypted PDFs, macro-enabled Office files, embedded executables, malformed archives, excessive compression ratio, excessive page count, and parser timeout.

- [ ] Parser output is `ParsedDocument(title, authors, published_at, identifiers, sections, pages, tables, figures, references, warnings)` with stable source positions. Preserve page/section information needed for citations.

- [ ] Run parsing in a resource-limited worker subprocess/container: no network, read-only input, bounded CPU/memory/time, temporary directory cleanup, and no shell interpolation.

- [ ] Normalize Unicode, strip active HTML/script/style, retain table text with coordinates, and record unsupported figure/table warnings rather than silently dropping them.

- [ ] Golden fixtures must prove exact extracted title, page text, table cells, figure captions, DOI/PMID metadata, and failure codes.

## Task 6: Deduplicate, Version, Normalize, and Chunk

**Files:** `chunking.py`, `repository.py`, tests

- [ ] Exact SHA-256 duplicate in the same workspace reuses the existing document version and records `duplicate_exact`; cross-tenant hashes never expose another tenant's record.

- [ ] Same approved external identifier with changed checksum creates the next immutable version and updates `current_version_id` only after the new version is ready.

- [ ] Store canonical normalized JSON in S3 with checksum and parser version. Promote original binary from quarantine to evidence prefix using copy with KMS and metadata; verify destination before marking ready.

- [ ] Chunk by section with target 600 tokens, maximum 900, overlap 80, never crossing document-version boundary. Stable citation ID format:

```text
doc:{document_id}:v:{version}:chunk:{ordinal}
```

- [ ] Persist every chunk text hash, token count, page/section location, and normalized object hash. A rerun with the same parser/chunker version produces identical chunks and hashes.

- [ ] Tests cover exact duplicates, version increments, tenant privacy, deterministic chunking, table chunks, oversized section splitting, and promotion failure recovery.

## Task 7: Add Evidence Library and Ingestion Status APIs

**Files:** `routers/evidence_documents.py`, schemas, API tests, OpenAPI

- [ ] Implement list/detail/version/event routes with cursor pagination, source/status/type/date filters, and exact tenant scope.

- [ ] `GET /v1/ingestion-jobs/{job_id}` returns safe step/status/event information. It never returns quarantine keys or scanner-sensitive matches.

- [ ] Add reprocess route restricted to workspace admin, requiring target parser/chunker version and idempotency key. Reprocessing creates a new processing attempt and never mutates an approved version.

- [ ] Add soft-delete/retention-request route; physical deletion is a separate authorized retention job and preserves required audit/legal-hold state.

- [ ] Generate OpenAPI and TypeScript client; API tests cover permission, cross-tenant, pagination, ready-only content access, blocked details, and idempotent reprocess.

## Task 8: Add Operator Commands and Runbook

**Files:** `scripts/reprocess_document.py`, `docs/production/runbooks/ingestion.md`, dashboards/alarms

- [ ] CLI requires environment, tenant, workspace, document/version, reason, actor, and dry-run/apply mode. It uses API/service credentials instead of direct table writes in production.

- [ ] Runbook covers stuck upload, checksum mismatch, malware, suspected PHI, parser crash, duplicate, wrong metadata, quarantine retention, safe download for security review, reprocess, and deletion escalation.

- [ ] Metrics/alarms: uploads, bytes, scan latency/error/infected, PHI blocked/unknown, parser failure by type, queue age, ready latency, duplicates, and quarantine age.

## Task 9: End-to-End Staging Validation

- [ ] Browser/API uploads each supported clean format and reaches `ready` with correct metadata/chunks.
- [ ] EICAR and synthetic PHI fixtures remain quarantined and unavailable to retrieval.
- [ ] Cross-tenant list/detail/object URL attempts fail.
- [ ] Duplicate finalize and duplicate SQS delivery do not duplicate versions/chunks.
- [ ] Presigned URL expiration, KMS, object version, and checksum are verified.
- [ ] Record staging evidence and mark Plan 5 complete only after the runbook exercise and alarms pass.

## Exit Gate

- Supported non-PHI files reach immutable, versioned, citation-addressable evidence objects.
- Malware, suspected PHI, unknown classification, integrity mismatch, unapproved source, and unsafe format fail closed.
- S3 objects and PostgreSQL records remain tenant/workspace scoped with checksum/version lineage.
- Reprocessing and duplicate delivery are idempotent.
- Evidence library/status APIs and OpenAPI/TypeScript client pass tests.
- Quarantine/ready latency and failure alarms work in staging.
- No uploaded content reaches retrieval or a model before `ready`.

## Handoff

Plan 6 indexes only `ready` document versions. It consumes `document_chunks` and evidence-object hashes; it does not parse source binaries again.

