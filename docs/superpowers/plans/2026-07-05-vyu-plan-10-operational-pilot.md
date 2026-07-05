# VYU Operational and Controlled-Pilot Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the integrated VYU release is secure, observable, recoverable, supportable, quality-gated, and suitable for a controlled non-PHI research pilot.

**Architecture:** This plan adds no new product scope. It validates the exact staged release across threat controls, tenant isolation, AI/evidence quality, load, resilience, recovery, incident response, operations, support, user training, and formal approval. Evidence is bound to immutable source/image/infrastructure/model/index/policy versions.

**Tech Stack:** OpenTelemetry/CloudWatch, GitHub Actions, AWS Security services, load-test tooling, OWASP/NIST-aligned controls, pytest/Playwright, retrieval/synthesis evaluation runners, RDS/S3 recovery, incident and release runbooks.

---

## Entry Gate

- Plans 1-9 are complete in staging.
- The exact release candidate Git SHA, image digests, Terraform plan/apply, migration revision, model/prompt/index/methodology/governance versions, and OpenAPI hash are frozen.
- Scope remains non-PHI, non-patient-specific, and research-support only.

## Task 1: Reconcile Intended Use, Data Inventory, and Threat Model

- [ ] Update intended-use, forbidden-use, privacy data flow, security architecture, threat model, source inventory, provider inventory, and retention/deletion matrix to match deployed behavior.
- [ ] Trace every data class from browser through CloudFront/ALB/ECS/RDS/S3/SQS/logs/providers/backups/deletion. Record owner, classification, purpose, legal/contract basis, region, encryption, retention, deletion, and external recipient.
- [ ] Threat model covers authentication/session, tenant isolation, service credentials, uploads/parsers, SSRF, source content prompt injection, model/provider, queues/idempotency, webhooks, exports, audit tampering, CI/CD, Terraform state, dependencies/images, insiders, backup, and support access.
- [ ] Every high/critical threat has an implemented control, test/evidence owner, monitoring signal, and residual-risk decision. Documentation-only controls do not count as implementation.
- [ ] Product, security, privacy, clinical/evidence, and operations owners sign the exact version.

## Task 2: Run Automated Security and Supply-Chain Gates

- [ ] Required CI gates: secret scan including history, SAST, Python/Node dependency vulnerabilities and licenses, container scan, SBOM, IaC scan, Terraform policy, DAST against staging, OpenAPI fuzzing, and signed image/provenance verification.
- [ ] Release policy blocks exploitable critical/high findings. Exceptions require finding ID, scope, compensating control, owner, expiry, and approving security owner.
- [ ] Verify no secret in Git, GitHub logs/artifacts, Terraform state/outputs, Docker history, frontend bundle/source maps, CloudWatch logs, S3 metadata, error responses, or support exports.
- [ ] Verify all GitHub actions/images/providers/dependencies are immutable or lock-controlled and update automation opens reviewed pull requests.
- [ ] Store scan reports with tool/database versions, timestamps, target hashes, suppressions, and result summary in release evidence.

## Task 3: Prove Authentication, Authorization, and Tenant Isolation

- [ ] Execute the complete role/action matrix for researcher, reviewer, workspace admin, tenant admin, compliance, viewer, service account, unauthenticated, suspended user, revoked credential, and expired session.
- [ ] Attempt horizontal/vertical access using changed tenant/workspace/resource IDs across API, BFF, presigned uploads/downloads, queues, admin, audit, reports, and browser deep links.
- [ ] Verify RLS blocks direct wrong-scope database sessions even when application filters are intentionally omitted in the test.
- [ ] Test Cognito PKCE state/nonce/code replay/open redirect, JWT issuer/audience/algorithm/token-use/expiry, session fixation/rotation/logout, CSRF, CORS, cookie flags, MFA, and service credential scope/revocation.
- [ ] Any cross-tenant disclosure or unauthorized mutation is release-blocking with no severity downgrade.

## Task 4: Run Upload, Source, Prompt, and Model Abuse Tests

- [ ] Upload: malware/EICAR, polyglot, double extension, MIME spoof, zip bomb, malformed PDF/DOCX, macro, encrypted file, oversized file, path/key injection, parser timeout, suspected PHI, and scanner failure.
- [ ] Connector: SSRF/redirect, DNS rebinding defenses, huge response, invalid JSON, 429/5xx storm, retraction/correction, unapproved source/tool/use, replay tamper, and license/retention gate.
- [ ] Prompt/model: instructions in source text, fabricated citation IDs, unsupported claim, patient-specific request, PHI request, jailbreak, encoded injection, refusal, malformed structured output, context overflow, provider timeout/rate limit, and fallback policy abuse.
- [ ] Review/export: direct worker-message injection, stale approval, self-approval, role mismatch, version swap, URL reuse/expiry, export content injection, and audit failure.
- [ ] Each case has expected blocked/abstained/review state and persisted audit/alert evidence.

## Task 5: Lock Evidence and AI Quality Gates

- [ ] Freeze licensed/versioned synthetic and expert-adjudicated non-PHI evaluation datasets with checksums and held-out release splits.
- [ ] Retrieval metrics include Recall@5/10/20, MRR@10, nDCG@10, retraction exclusion, source-policy violations, empty-result correctness, freshness, and latency.
- [ ] Synthesis metrics include structured-output validity, citation validity/precision, claim faithfulness, unsupported claim rate, abstention correctness, contradiction/limitation disclosure, prohibited-use response, injection resistance, reviewer agreement, latency, and cost.
- [ ] Governance metrics include correct review/block/export decision, no high-risk bypass, warning correctness, score calculation/version, and reviewer override handling.
- [ ] Clinical/evidence owners approve thresholds based on the pilot use case. A critical safety case failure blocks release even when aggregate metrics pass.
- [ ] Record per-case outputs and adjudication, not only aggregate scores.

## Task 6: Load, Scale, and Cost Validation

- [ ] Define pilot workload: concurrent users, searches/hour, uploads/hour, average/max document size, connector calls, embedding chunks, model tokens, review queue, and exports.
- [ ] Load test read APIs, research submission, status polling, queue/worker throughput, retrieval, upload presign/finalize, review, and export without using unapproved live-provider volume.
- [ ] Verify API p95 under 500 ms for non-job routes at pilot load, no error-budget breach, queue age within job SLO, database pool below safe threshold, and ECS autoscaling stabilizes without thrash.
- [ ] Soak for the approved operating window to detect connection leaks, memory growth, stuck leases, duplicate work, log/metric cardinality, and cost anomalies.
- [ ] Produce per-research cost model for compute, RDS, storage, egress, source, embedding, generation, telemetry, and review. Configure budget/anomaly alerts.

## Task 7: Failure and Resilience Exercises

- [ ] Terminate API and worker tasks during requests/jobs; verify load balancer recovery, lease expiry, idempotent continuation, and no duplicated charged operation.
- [ ] Simulate RDS failover, exhausted pool, slow query, S3/SQS/provider timeout, DLQ, expired secret, Cognito outage, connector outage, malformed provider response, and telemetry outage.
- [ ] Verify bounded retries, circuit/health state, user-visible safe status, alarms, runbook actions, recovery, and audit continuity.
- [ ] Redrive DLQ in staging with dry-run selection and prove terminal jobs are not repeated.
- [ ] Verify deployment circuit breaker, previous task definition rollback, feature-disable/config rollback, and database forward-fix decision.

## Task 8: Backup, Restore, and Disaster Recovery Drill

- [ ] Record known RDS/S3/audit fixtures and checksums, make changes over time, restore RDS to an isolated point, restore exact S3 versions, and validate tenant/RLS/lineage/audit/index metadata.
- [ ] Rebuild disposable retrieval indexes from authoritative document/chunk manifests and compare manifest hashes/quality.
- [ ] Measure RPO and RTO from incident declaration through verified service restoration. Pilot targets are RPO <= 15 minutes and RTO <= 4 hours.
- [ ] Test accidental deletion, corrupted logical record, lost task definition, and region/account access disruption scenarios documented for the pilot architecture.
- [ ] Record commands, operators, timestamps, evidence, gaps, cleanup, and owner approval. Snapshot existence is not restore evidence.

## Task 9: Observability, Alert, and On-Call Validation

- [ ] Verify dashboards for edge/API/ECS/RDS/SQS/connectors/retrieval/models/governance/review/export/audit/backups and business-quality trends.
- [ ] Trigger every critical alarm in staging and confirm delivery, deduplication, severity, owner, runbook link, acknowledgement, escalation, and resolution.
- [ ] Define SLI calculations and monthly SLO/error-budget report for API availability, route latency, research success, queue age, audit persistence, review bypass, and restore readiness.
- [ ] Control metric/log cardinality and retention. Query by request/trace/run/job/audit ID without searching sensitive content.
- [ ] Create on-call schedule, primary/secondary ownership, escalation contacts, severity definitions, and communication channels.

## Task 10: Incident Response Exercise

- [ ] Run a tabletop and technical exercise for suspected cross-tenant exposure or leaked provider credential.
- [ ] Exercise detection, containment, credential revocation/rotation, ECS redeploy, evidence preservation, tenant-impact analysis, audit reconstruction, communications escalation, recovery, and retrospective.
- [ ] Separate security/privacy/legal/customer communication decisions by authorized owner. Junior engineers do not decide notification obligations.
- [ ] Record time to detect/contain/recover, evidence gaps, assigned corrective actions, due dates, and retest.

## Task 11: User, Reviewer, Admin, and Support Readiness

- [ ] Publish user guide for intended use, prohibited use, search/evidence/citations, uncertainty, Trust Score meaning, review state, exports, feedback, and limitations.
- [ ] Publish reviewer guide for methodology, evidence inspection, conflicts/retractions, decisions, comments, escalation, independence, and audit responsibility.
- [ ] Publish admin guide for memberships, policies, source/model/index health, service credentials, audit, retention, and safe support access.
- [ ] Publish support runbooks for login, stuck job, source outage, suspected wrong citation, evidence dispute, export, access, deletion, security/privacy escalation, and status communication.
- [ ] Train pilot users/reviewers/admin/support and record completion. Validate comprehension with scenario exercises.

## Task 12: Customer and Vendor Trust Package

- [ ] Package approved intended use/limitations, architecture/data flow, security controls, subprocessor/provider list, data retention/deletion, source methodology, AI/evidence methodology, incident process, availability/support, audit export, and current independent assessment summaries.
- [ ] Legal/privacy/security owners approve privacy policy, terms, DPA, vendor terms, source licenses, and non-PHI customer obligations. Do not claim HIPAA, SOC 2, FDA, medical-device, or other certification without qualified evidence.
- [ ] Document customer onboarding/offboarding, tenant bootstrap, access review, data export/deletion, credential revocation, and evidence retention.

## Task 13: Build the Immutable Release Evidence Bundle

- [ ] Bundle references exact Git SHA, signed image digests, SBOMs, Terraform plan/apply IDs, AWS accounts/regions, migration revision, OpenAPI hash, model/embedding snapshots, prompt/index/methodology/governance/source policy versions, evaluation dataset/results, scan reports, load/resilience/restore/incident evidence, and documentation hashes.
- [ ] Verify every referenced artifact hash and reject missing/stale/wrong-environment evidence.
- [ ] Required approvals: product, engineering, security, privacy, clinical/evidence, operations/SRE, and legal/regulatory owner for the intended-use position.
- [ ] Store signed canonical bundle in the Object Lock audit bucket. Local `outputs/pilot_release_decision.json` is excluded and cannot approve release.

## Task 14: Controlled Pilot Launch and Observation

- [ ] Define named pilot tenants/users, public/non-PHI data scope, duration, permitted workflows, success/failure metrics, support hours, incident contacts, stop criteria, rollback authority, and feature flags.
- [ ] Start with low concurrency and limited approved sources/model policy. Monitor every research run/review/export and daily quality/safety/operations summary.
- [ ] Stop or restrict pilot on cross-tenant risk, PHI intake, unsafe recommendation, unsupported-claim threshold breach, review bypass, audit loss, unresolved critical vulnerability, restore failure, or repeated severe outage.
- [ ] Collect structured user/reviewer feedback linked to run IDs without copying sensitive content into tickets.
- [ ] At observation end, review metrics, incidents, disputes, support load, cost, quality, corrective actions, and residual risk before any broader availability decision.

## Exit Gate

- Security/privacy/threat/data reviews match deployed state.
- Automated and manual security gates pass with approved time-bounded exceptions only.
- Tenant isolation and critical abuse cases pass.
- Locked retrieval/synthesis/governance quality gates and expert adjudication pass.
- Load, soak, cost, resilience, rollback, secret rotation, DLQ, restore, and incident exercises pass.
- SLO dashboards, alarms, on-call, runbooks, support, and training are active.
- Trust/customer/vendor documents are owner-approved and make no unsupported compliance claims.
- Immutable release evidence has all required approvals.
- Controlled pilot completes its observation window or remains explicitly limited; general availability is a separate approved decision.

## Final Definition of Production

VYU may be called production only when Plans 1-10 are complete for the same immutable release and the controlled-pilot decision explicitly authorizes the intended environment and scope. Source files, unit tests, local artifacts, a successful deploy, or an API key alone are not sufficient evidence.

