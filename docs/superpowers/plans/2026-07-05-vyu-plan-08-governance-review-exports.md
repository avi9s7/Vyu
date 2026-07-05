# VYU Governance, Human Review, and Report Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind evidence methodology, Trust Score, Governance Box, human review, and professional report export into one immutable production workflow.

**Architecture:** A versioned governance policy evaluates the persisted retrieval, methodology, synthesis, and citation records. The result is append-only and determines whether export is blocked, requires review, or is eligible. Review events never rewrite history. Export renders one exact approved answer/governance version to S3 and keeps its limitations, citations, versions, and approvals attached.

**Tech Stack:** PostgreSQL/Alembic, FastAPI, SQS, S3, existing VYU evidence/governance/review/report logic, Jinja2, WeasyPrint or approved PDF renderer, python-docx, SMTP/SES notification adapter, pytest, Playwright in Plan 9.

---

## Entry Gate

- Plans 1-4, 6, and 7 complete.
- Clinical/evidence owner has reviewed initial methodology and Trust Score semantics.
- Report formats and required legal/product labels are approved.

## Task 1: Version Methodology and Governance Policy

**Files:** methodology/governance policy repositories, migration `0007_governance_review_export.py`, tests

- [ ] Add immutable `methodology_versions`, `methodology_assessments`, `contradictions`, `governance_policy_versions`, `trust_scores`, `governance_boxes`, `governance_warnings`, `review_tasks`, `review_events`, and `report_exports`.

- [ ] Every record carries tenant/workspace/research/answer scope and the source/index/model/prompt/methodology/governance policy versions needed for reconstruction.

- [ ] Status/decision enums are database constrained. Enable/force RLS. Approved/terminal records reject update/delete through triggers; corrections create new versions/events.

- [ ] Import existing deterministic methodology/Trust Score configuration as version `v1-pilot` only after owner approval and hash verification. Existing local output JSON is not imported as production approval.

- [ ] Migration/repository tests prove scope, append-only behavior, version uniqueness, and complete lineage foreign keys.

## Task 2: Integrate Evidence Methodology and Contradiction Assessment

**Files:** methodology service, contradiction service, worker handler, tests

- [ ] Adapt existing deterministic evidence profiles and methodology records behind production repositories. Remove direct synthetic-corpus and SQLite assumptions.

- [ ] Assess study design, directness, limitations, consistency, precision, publication/retraction/correction flags, and source policy using the approved methodology version.

- [ ] Contradictions link exact document/chunk/claim identifiers and explain direction/type without resolving clinical truth automatically.

- [ ] Low confidence, serious limitation, retracted evidence, conflicting primary outcomes, unsupported claim, or methodology failure forces human review or block per policy.

- [ ] Reviewer ratings are separate append-only events that reference the automated assessment and include actor, reason, previous/new value, timestamp, and policy authorization.

- [ ] Tests use locked cases for strong/weak/conflicting/retracted/preprint evidence, wrong scope, unauthorized override, version change, and duplicate worker delivery.

## Task 3: Calculate and Persist Trust Score

**Files:** production trust service, policy tests, evaluation fixtures

- [ ] Trust Score components and weights come only from an approved governance policy. Store every normalized component, weight, raw evidence input reference, formula version, and final bounded score.

- [ ] Score is explanatory, not a probability of clinical truth. UI/report labels must state this limitation.

- [ ] Missing required input does not default to a favorable score. It creates `insufficient_data`, warning, and review/block decision.

- [ ] Reviewer override creates a new override record with reason and authorization; it does not alter the calculated score. Governance Box displays calculated and effective values.

- [ ] Tests prove deterministic calculation, bounds, missing input, policy versioning, unauthorized override, and no export decision based solely on score.

## Task 4: Build the Governance Box and Export Decision

**Files:** governance service, worker handler, API schema/tests

- [ ] Governance Box includes research scope, sources searched/blocked, retrieval/index versions, evidence summary, contradictions, model/prompt/provider, citation validation, Trust Score breakdown, warnings, intended-use limitations, review requirement/state, export decision, and audit correlation ID.

- [ ] Decision states: `blocked`, `review_required`, `eligible`, `exported`, `superseded`. `eligible` requires successful synthesis/citations, no blocking warning, allowed intended use, and policy conditions.

- [ ] High-risk conditions always require review even when score is high. A blocked condition cannot be overridden by a general reviewer; policy specifies roles that may resolve each warning.

- [ ] `GET /v1/research/searches/{id}/governance` returns user-safe full breakdown and exact version links. Cross-tenant and incomplete governance tests pass.

- [ ] Duplicate processing returns the existing same-input governance version; changed answer/methodology/policy creates a new version.

## Task 5: Complete Review Assignment and Decision Workflow

**Files:** review repository/service/routes, notification adapter, tests

- [ ] Review task stores priority, reasons, required roles, assignment, due time, status, exact answer/governance versions, and escalation state.

- [ ] Events: `created`, `assigned`, `commented`, `approved`, `changes_requested`, `rejected`, `escalated`, `expired`, `superseded`. State transitions are explicit and tested.

- [ ] Required-role separation: creator cannot approve own high-risk export when policy requires independent review; clinical/evidence, privacy, legal, or compliance role requirements are additive.

- [ ] Optimistic version prevents two reviewers from silently overwriting decisions. Second conflicting decision returns `409 conflict` and current state.

- [ ] Notifications carry only task ID, safe reason category, due time, and link; no document, prompt, answer, or sensitive comment content.

- [ ] APIs support scoped queue filters, detail, assignment, comment, decision, escalation, and history. Every mutation is idempotent and audited.

- [ ] Tests cover role matrix, self-review restriction, stale version, double approval, changes requested leading to new answer version, escalation, expiration, notification failure, and wrong tenant.

## Task 6: Render Versioned PDF and DOCX Reports

**Files:** report contracts/templates/renderers, export worker, golden tests

- [ ] Supported first-release formats are PDF and DOCX. HTML may be an internal intermediate; PPTX/XLSX remain disabled until separately specified/tested.

- [ ] Required sections: title/metadata, question/scope, executive summary, findings with claim citations, evidence table, uncertainty/contradictions, methodology, Trust Score/Governance Box, limitations/intended use, source list, model/prompt/index/policy versions, review history/sign-off, audit ID, generated timestamp, and status watermark.

- [ ] Render from persisted records only; never ask the model to generate the final report file. Escape untrusted text and prohibit active HTML/external resource fetches.

- [ ] Embed citation links/footnotes to exact evidence records. Missing citation or governance data blocks rendering.

- [ ] Golden tests extract PDF/DOCX text and assert required sections, citation IDs, watermark, sign-off, versions, and limitations. Visual regression checks rendered pages for clipping/blank pages/table overflow.

## Task 7: Gate, Store, and Download Exports

**Files:** report export route/service/repository, S3 adapter, tests

- [ ] `POST /v1/report-exports` requires exact research/answer/governance version, format, idempotency key, and actor permission. It re-evaluates export eligibility in the transaction that creates the job.

- [ ] Review-required export needs approved, unexpired, non-superseded exact-version review events. Any version mismatch blocks.

- [ ] Worker renders, checks checksum/size/media type, writes immutable S3 object version, persists export metadata, emits audit event, then marks completed. Object key contains export ID/version and never overwrites.

- [ ] Download route returns a single-object short-lived presigned URL after authorization and audit. It does not expose bucket/key and is disabled for blocked/superseded/deleted exports.

- [ ] Tests cover unauthorized, pending/rejected/expired review, version mismatch, duplicate request/message, render failure, S3 failure, checksum, URL expiry/scope, and audit failure.

## Task 8: Archive Audit and Release Evidence

**Files:** audit canonicalizer/archive job/reconstruction API/tests

- [ ] Canonicalize selected material events, hash each payload, batch with previous-batch hash, write PostgreSQL archive metadata, and store canonical batch in versioned Object Lock audit bucket.

- [ ] Archive failure alarms and prevents release-evidence closure; it does not delete database events.

- [ ] Admin reconstruction endpoint returns ordered source, retrieval, model, answer, governance, review, and export lineage for one research run without secret/raw restricted payloads.

- [ ] Tests detect event tampering, missing event, wrong previous hash, object version mismatch, wrong scope, and duplicate archive job.

## Task 9: Governance and Review UI Contract Handoff

- [ ] Regenerate OpenAPI/TypeScript client for governance, review, and export routes.
- [ ] Provide fixture contracts only under frontend tests for eligible, review-required, blocked, approved, changes-requested, rejected, superseded, and exported states.
- [ ] Document user-visible labels and prohibited misleading terms. “Trust Score” includes tooltip/definition and is never labeled accuracy probability.
- [ ] Plan 9 implements screens against these stable contracts; backend API tests remain authoritative for authorization and state transitions.

## Task 10: Staging Governance Exercise

- [ ] Run one eligible public-literature case, one conflicting case, one retracted case, one unsupported-citation attack, and one prompt-injection case.
- [ ] Prove blocked cases cannot export by direct API, duplicate request, stale review, admin UI, or worker message injection.
- [ ] Complete reviewer assignment/approval and generate PDF/DOCX; verify content, S3 version/checksum, signed URL, audit archive, and reconstruction.
- [ ] Force notification/render/S3/archive failures and verify state, retries, alarms, and no false completion.
- [ ] Clinical/evidence owner reviews methodology/score/warnings; product/legal owners review report labels/limitations.
- [ ] Bind evidence to exact versions and mark Plan 8 complete.

## Exit Gate

- Methodology, Trust Score, Governance Box, review, and exports are persisted/versioned/scoped.
- High-risk results cannot bypass required independent review.
- Corrections and overrides are append-only and attributable.
- PDF/DOCX preserve citations, limitations, governance, review history, audit ID, and all version lineage.
- Downloads are short-lived, authorized, and audited.
- Audit reconstruction and tamper detection pass.
- Locked governance/safety cases and expert review pass for the exact release.

## Handoff

Plan 9 completes the browser workflows using the generated client. Plan 10 validates monitoring, security, recovery, support, training, and pilot governance around the integrated system.

