# Production Operator Runbook

## Purpose

This runbook describes the current production-shaped local workflow for Vyu. It is intended for operators and engineers who need to generate artifacts, persist queryable records, inspect stored runs, and run readiness checks before pilot-style review.

The workflow is still local and deterministic. It does not replace production deployment, security, privacy, regulatory, or clinical validation.

## Prerequisites

- Run commands from the repository root.
- Use Python 3.11 or newer.
- Confirm the source registry contains approved records for local artifact generation:
  - `dummy_corpus`
  - `golden_questions`
- Confirm the intended tenant/workspace scope for this local run:
  - tenant: `local_tenant`
  - workspace: `local_workspace`

## Local Deployment Package and Release Evidence Rehearsal

This rehearsal validates the local serverless-style package boundary and produces unsigned release evidence. It is still local-only; it does not deploy cloud infrastructure, provision IAM, or replace CI/CD approval gates.

### Validate Deployment Config and Package Metadata

```bash
python scripts/validate_deployment_config.py --env-file config/deployment.local.env
python scripts/validate_deployment_package.py --manifest deploy/serverless/package.manifest.json
```

Use `config/deployment.local.example.env` as the non-secret template for a real local `config/deployment.local.env`. The validator fails closed on placeholder secrets unless `--allow-placeholder-secret` is explicitly used for template checks.

### Build Package Inventory, Archive, and Evidence

```bash
python scripts/plan_deployment_package.py --manifest deploy/serverless/package.manifest.json --output outputs/deployment_package_inventory.json
python scripts/build_deployment_archive.py --manifest deploy/serverless/package.manifest.json --archive outputs/vyu_deployment_package.zip --inventory outputs/deployment_package_inventory.json
python scripts/write_deployment_package_evidence.py --manifest deploy/serverless/package.manifest.json --archive outputs/vyu_deployment_package.zip --inventory outputs/deployment_package_inventory.json --output outputs/deployment_package_evidence.json
python scripts/check_deployment_release_package.py --manifest deploy/serverless/package.manifest.json --archive outputs/vyu_deployment_package.zip --inventory outputs/deployment_package_inventory.json --evidence outputs/deployment_package_evidence.json --output outputs/deployment_release_package_checklist.json
```

Expected result:

- `outputs/deployment_package_inventory.json` records deterministic package paths, sizes, and hashes.
- `outputs/vyu_deployment_package.zip` is reproducible and excludes local secrets, generated caches, and upstream review clones.
- `outputs/deployment_package_evidence.json` has `"status": "complete"`.
- `outputs/deployment_release_package_checklist.json` has `"status": "ready"`.

### Record Command Transcripts, Bundle Evidence, and Review Handoff

```bash
python scripts/write_deployment_command_transcript.py --command-json "[\"python\", \"scripts/validate_deployment_package.py\", \"--manifest\", \"deploy/serverless/package.manifest.json\"]" --purpose "validate deployment package manifest" --return-code 0 --stdout-file outputs/transcripts/validate_deployment_package.stdout --stderr-file outputs/transcripts/validate_deployment_package.stderr --artifact outputs/deployment_package_evidence.json --output outputs/transcripts/validate_deployment_package.json
python scripts/check_deployment_transcript_bundle.py --manifest deploy/serverless/package.manifest.json --transcript outputs/transcripts/validate_deployment_config.json --transcript outputs/transcripts/validate_deployment_package.json --transcript outputs/transcripts/plan_deployment_package.json --transcript outputs/transcripts/build_deployment_archive.json --transcript outputs/transcripts/write_deployment_package_evidence.json --transcript outputs/transcripts/check_deployment_release_package.json --transcript outputs/transcripts/smoke_test_deployment.json --output outputs/deployment_transcript_bundle.json
python scripts/build_deployment_release_evidence.py --package-evidence outputs/deployment_package_evidence.json --release-checklist outputs/deployment_release_package_checklist.json --transcript-bundle outputs/deployment_transcript_bundle.json --output outputs/deployment_release_evidence_summary.json
python scripts/review_deployment_release_evidence.py --summary outputs/deployment_release_evidence_summary.json --decision approve --reviewer-id deployment-operator --reviewer-role deployment_operator --comment "Deployment release evidence reviewed locally." --decided-at 2026-06-15T02:45:00Z --output outputs/deployment_release_review_decision.json
python scripts/build_deployment_release_handoff.py --summary outputs/deployment_release_evidence_summary.json --review outputs/deployment_release_review_decision.json --created-at 2026-06-15T03:00:00Z --output outputs/deployment_release_handoff.json
python scripts/build_deployment_release_handoff_archive.py --handoff outputs/deployment_release_handoff.json --created-at 2026-06-15T03:15:00Z --inventory outputs/deployment_release_handoff_inventory.json --archive outputs/deployment_release_handoff.zip
python scripts/prepare_deployment_release_channel.py --inventory outputs/deployment_release_handoff_inventory.json --archive outputs/deployment_release_handoff.zip --created-at 2026-06-15T03:30:00Z --channel local-release-channel --output outputs/deployment_release_channel_preparation.json
python scripts/accept_deployment_release_channel.py --preparation outputs/deployment_release_channel_preparation.json --decision approve --operator-id release-operator --operator-role deployment_operator --comment "Release channel preparation accepted for local publication." --decided-at 2026-06-15T03:45:00Z --output outputs/deployment_release_channel_acceptance.json
python scripts/prepare_deployment_release_channel_publication.py --acceptance outputs/deployment_release_channel_acceptance.json --publication-channel local-release-channel-publication --created-at 2026-06-15T04:00:00Z --output outputs/deployment_release_channel_publication_manifest.json
python scripts/build_deployment_release_channel_evidence.py --publication outputs/deployment_release_channel_publication_manifest.json --index-name local-release-channel-evidence-index --created-at 2026-06-15T04:15:00Z --output outputs/deployment_release_channel_evidence_index.json
python scripts/build_deployment_release_channel_export_summary.py --evidence-index outputs/deployment_release_channel_evidence_index.json --summary-name local-release-channel-evidence-export-summary --created-at 2026-06-15T04:30:00Z --output outputs/deployment_release_channel_export_summary.json
python scripts/build_deployment_release_channel_target_readiness.py --export-summary outputs/deployment_release_channel_export_summary.json --readiness-name local-release-channel-target-readiness --created-at 2026-06-15T04:45:00Z --output outputs/deployment_release_channel_target_readiness.json
python scripts/decide_deployment_release_channel_target.py --target-readiness outputs/deployment_release_channel_target_readiness.json --decision choose --target-family serverless_function --operator-id target-operator --operator-role deployment_operator --rationale "Serverless function selected for provider planning." --decided-at 2026-06-15T05:00:00Z --output outputs/deployment_release_channel_target_decision.json
python scripts/build_deployment_release_channel_provider_preflight.py --target-decision outputs/deployment_release_channel_target_decision.json --preflight-name local-release-channel-provider-planning-preflight --created-at 2026-06-15T05:30:00Z --output outputs/deployment_release_channel_provider_preflight.json
python scripts/decide_deployment_release_channel_provider.py --provider-preflight outputs/deployment_release_channel_provider_preflight.json --decision proceed --planning-track serverless_provider_requirements_review --operator-id provider-operator --operator-role deployment_operator --rationale "Provider planning approved from local preflight." --decided-at 2026-06-15T06:00:00Z --output outputs/deployment_release_channel_provider_decision.json
```

Expected result:

- `outputs/deployment_transcript_bundle.json` has `"status": "ready"` only when every required manifest command has passing transcript evidence.
- `outputs/deployment_release_evidence_summary.json` has `"status": "ready"` only when package evidence, release checklist, and transcript bundle agree.
- `outputs/deployment_release_review_decision.json` has `"status": "approved"` only for an approve decision against a ready summary.
- `outputs/deployment_release_handoff.json` has `"status": "ready"` only when the summary and approved review decision are hash-bound.
- `outputs/deployment_release_handoff_inventory.json` has `"status": "ready"` and records `archive.sha256`, `artifacts[].archive_entry`, `artifacts[].hash_matches_expected`, `handoff_status_ready`, `release_evidence_paths_present`, `recorded_hashes_match_files`, `archive_entries_match_inventory`, `archive_entry_hashes_match_inventory`, and `archive_metadata_deterministic`.
- `outputs/deployment_release_handoff.zip` contains only the handoff bundle and hash-bound referenced release evidence JSON files; it must not contain local secret config or generated caches.
- `outputs/deployment_release_channel_preparation.json` has `"status": "ready"` and records `inventory_sha256`, `archive.expected_sha256`, `archive.hash_matches_expected`, `artifact_hashes.handoff_inventory_sha256`, `artifact_hashes.handoff_archive_sha256`, `inventory_status_ready`, `inventory_checks_passed`, `inventory_artifact_hashes_match`, `archive_hash_matches_inventory`, and `next_actions[]`.
- `outputs/deployment_release_channel_acceptance.json` has `"status": "accepted"` for an approve decision against ready preparation evidence, and records `acceptance_id`, `preparation.sha256`, `preparation_status_ready`, `preparation_checks_passed`, `preparation_archive_hash_bound`, `operator_metadata_present`, and `approve_requires_ready_preparation`.
- `outputs/deployment_release_channel_publication_manifest.json` has `"status": "ready"` only when the acceptance record is accepted, approval-bound, has no blocking reasons, and includes accepted preparation/package/hash evidence.
- `outputs/deployment_release_channel_publication_manifest.json` records `acceptance.sha256`, `acceptance.status`, `acceptance_decision_approves`, `acceptance_blocking_reasons_absent`, `preparation_hash_present`, `preparation_status_ready`, `preparation_inventory_sha256_present`, `preparation_archive_hash_bound`, `publication_steps[]`, `local_only_limits[]`, and `local_only_limits_recorded`.
- `outputs/deployment_release_channel_evidence_index.json` has `"status": "ready"` only when the publication manifest is ready, publication checks passed, acceptance/preparation hashes are present, the handoff archive remains hash-bound, and all required evidence items are present.
- `outputs/deployment_release_channel_evidence_index.json` records `publication.sha256`, `publication.status`, `publication_checks_passed`, `acceptance_sha256_present`, `acceptance_status_accepted`, `decision_approves`, `preparation_sha256_present`, `preparation_status_ready`, `preparation_inventory_sha256_present`, `handoff_archive_hash_bound`, `required_evidence_items_present`, `evidence_items[].name`, `evidence_items[].sha256`, `summary.required_evidence_item_count`, and `summary.present_required_evidence_item_count`.
- `outputs/deployment_release_channel_export_summary.json` has `"status": "ready"` only when the evidence index is ready, every evidence-index check passed, required evidence counts are complete, the handoff archive remains hash-bound, package/operator metadata is present, and review checklist items are recorded.
- `outputs/deployment_release_channel_export_summary.json` records `evidence_index.sha256`, `evidence_index.status`, `evidence_index_checks_passed`, `publication_manifest_sha256_present`, `acceptance_record_sha256_present`, `preparation_manifest_sha256_present`, `handoff_inventory_sha256_present`, `handoff_archive_hash_bound`, `release_evidence_summary_sha256_present`, `release_review_decision_sha256_present`, `package_evidence_sha256_present`, `required_evidence_counts_complete`, `evidence_hashes.evidence_index_sha256`, `evidence_hashes.publication_manifest_sha256`, `required_evidence_items[].name`, `optional_evidence_items[].name`, `review_checklist[]`, `blocking_reasons`, and `summary.review_checklist_item_count`.
- `outputs/deployment_release_channel_target_readiness.json` has `"status": "ready"` only when the export summary is ready, evidence-index hash binding is intact, required evidence counts are complete, no provider is selected, and target handoff checklist items are recorded.
- `outputs/deployment_release_channel_target_readiness.json` records `export_summary.sha256`, `export_summary.status`, `export_summary_status_ready`, `evidence_index_sha256_present`, `evidence_index_sha256_matches_export_summary`, `required_evidence_counts_complete`, `selected_target_provider_absent`, `provider_configuration_empty`, `candidate_target_families[]`, `handoff_checklist[]`, `target_selection_scope`, `local_only_limits[]`, `blocking_reasons`, and `summary.handoff_checklist_item_count`.
- `outputs/deployment_release_channel_target_decision.json` has `"status": "selected"` only when the target-readiness note is ready, every target-readiness check passed, the operator decision is `choose`, and the selected target family appears in `candidate_target_families[]`.
- `outputs/deployment_release_channel_target_decision.json` records `target_readiness.sha256`, `target_readiness.status`, `decision.value`, `decision.selected_target_family`, `operator.id`, `operator.role`, `target_readiness_checks_passed`, `target_readiness_blocking_reasons_absent`, `target_family_candidates_present`, `choose_requires_candidate_target_family`, `block_or_defer_requires_no_selected_target_family`, `target_selection_scope_local_only`, `selected_target_provider`, `provider_configuration`, `no_target_provider_selected`, `no_provider_configuration_recorded`, `export_summary_sha256_present`, `evidence_index_sha256_present`, `local_only_limits[]`, `handoff_checklist[]`, `next_actions[]`, `blocking_reasons`, and `summary.next_action_count`.
- `outputs/deployment_release_channel_provider_preflight.json` has `"status": "ready"` only when the target decision is selected, every target-decision check passed, the decision value is `choose`, the selected target family is present and listed in `candidate_target_families[]`, no provider is selected, no provider configuration is recorded, and provider-planning requirements are recorded.
- `outputs/deployment_release_channel_provider_preflight.json` records `target_decision.sha256`, `target_decision.status`, `planning_scope`, `selected_target_family`, `selected_target_provider`, `provider_configuration`, `target_decision_status_selected`, `target_decision_checks_passed`, `target_decision_blocking_reasons_absent`, `decision_value_choose`, `selected_target_family_present`, `selected_target_family_in_candidates`, `target_selection_scope_local_only`, `no_target_provider_selected`, `no_provider_configuration_recorded`, `planning_requirements[]`, `next_actions[]`, `blocking_reasons`, `summary.planning_requirement_count`, and `summary.next_action_count`.
- `outputs/deployment_release_channel_provider_decision.json` has `"status": "approved"` only when the provider preflight is ready, every preflight check passed, the operator decision is `proceed`, an abstract provider-planning track is recorded, no provider is selected, and no provider configuration is recorded.
- `outputs/deployment_release_channel_provider_decision.json` records `provider_preflight.sha256`, `provider_preflight.status`, `planning_decision_scope`, `decision.value`, `decision.provider_planning_track`, `operator.id`, `operator.role`, `provider_preflight_status_ready`, `provider_preflight_checks_passed`, `provider_preflight_blocking_reasons_absent`, `proceed_requires_provider_planning_track`, `block_or_defer_requires_no_provider_planning_track`, `selected_target_family_present`, `planning_scope_preflight_only`, `target_selection_scope_local_only`, `no_target_provider_selected`, `no_provider_configuration_recorded`, `planning_requirements[]`, `next_actions[]`, `blocking_reasons`, and `summary.next_action_count`.

## Standard Local Production-Shaped Run

### 1. Regenerate Intake Metadata

```bash
python scripts/phase0_intake.py --manifest upstreams.yaml --root . --output UPSTREAM_LOCK.json --markdown docs/phase0/license-inventory.md
```

Expected result:

- `UPSTREAM_LOCK.json` is written.
- `docs/phase0/license-inventory.md` is written.
- Command exits `0`.

### 2. Generate Artifacts and Persist SQLite Records

```bash
python scripts/run_phase_outputs.py --root . --output-dir outputs --source-registry config/source_registry.example.json --sqlite-db outputs/production.sqlite
```

Expected result:

- `outputs/artifact_manifest.json` exists.
- `outputs/run_summary.json` exists.
- `outputs/evaluation/runs.jsonl` exists.
- `outputs/production.sqlite` exists.
- `outputs/phase2` through `outputs/phase7` contain persisted artifacts.
- SQLite contains:
  - artifact manifest
  - evaluation run
  - production audit events
  - production schema version metadata
  - production migration history
  - pending review task, when the generated governance box requires human review
  - evidence object, retrieval index, retrieval run, and production research-memory records
  - evidence methodology run and document-level assessment records
  - external evidence-grading request/response records for the placeholder provider boundary
  - connector health record
  - staged connector validation record
  - privacy approval records, when PHI/ePHI gate decisions are recorded for the run
  - readiness check results, after readiness checks are run

### 3. Inspect the Stored Run

```bash
python scripts/inspect_production_store.py --sqlite-db outputs/production.sqlite --run-id local-phase-output-run --tenant-id local_tenant --workspace-id local_workspace
```

Expected result:

- Command exits `0`.
- JSON output includes:
  - `artifact_manifest`
  - `evaluation_runs`
  - `review_tasks`
  - `evidence_object_records`
  - `retrieval_index_records`
  - `retrieval_run_records`
  - `production_research_memory_records`
  - `evidence_methodology_run_records`
  - `evidence_methodology_assessment_records`
  - `reviewer_evidence_rating_records`
  - `external_evidence_grading_request_records`
  - `external_evidence_grading_response_records`
  - `connector_health_records`
  - `connector_validation_records`
  - `privacy_approval_records`
  - `readiness_check_results`
  - `audit_events`

For the standard local fixture, `review_tasks` includes pending `review-local-phase-output-run` because the generated governance box requires human review. Reviewer decisions are visible in `review_tasks[].decision` after approval or rejection.
Evidence-memory and retrieval evidence is visible in `evidence_object_records`, `retrieval_index_records`, `retrieval_run_records`, and `production_research_memory_records`.
Evidence-grading methodology evidence is visible in `evidence_methodology_run_records` and `evidence_methodology_assessment_records`; reviewer adjustments are visible in `reviewer_evidence_rating_records`.
External AIdDea-like grading connector evidence is visible in `external_evidence_grading_request_records` and `external_evidence_grading_response_records`; local fixtures use placeholder endpoint URLs and replay transport rather than live vendor calls.
Connector readiness evidence is visible in `connector_health_records` and `connector_validation_records`.
Privacy gate decision evidence is visible in `privacy_approval_records` when approval records were persisted for the run.
Readiness check result evidence is visible in `readiness_check_results` after `scripts/check_production_readiness.py` is run.
Prompt-injection, citation-policy, and final report-export decisions are visible in `audit_events` as `prompt_injection_decision_recorded`, `citation_policy_decision_recorded`, and `report_export_decision_recorded` when report export is called with production storage.
The readiness command requires the reviewer decision and approved report export steps to run first for the standard pilot-style fixture.

The command should fail if tenant/workspace scope is wrong.

### 4. Inspect the Reviewer Queue

```bash
python scripts/inspect_review_queue.py --sqlite-db outputs/production.sqlite --tenant-id local_tenant --workspace-id local_workspace --user-id reviewer-1 --role reviewer --status pending --run-id local-phase-output-run
```

Expected result:

- Command exits `0` for an authorized reviewer principal.
- JSON output has `"reason": "review_queue_loaded"`.
- JSON output includes `review_tasks` filtered to pending tasks for the requested tenant/workspace and run.
- The standard local fixture includes `review-local-phase-output-run`.

The same list behavior is documented as a route contract in `docs/production/reviewer-queue-api.md`.

### 5. Record a Reviewer Decision

```bash
python scripts/record_review_decision.py --sqlite-db outputs/production.sqlite --review-id review-local-phase-output-run --tenant-id local_tenant --workspace-id local_workspace --user-id reviewer-1 --role reviewer --decision approve --comment "Evidence reviewed for export." --decided-at 2026-06-15T00:05:00Z
```

Expected result:

- Command exits `0` for an authorized reviewer principal.
- JSON output has `"reason": "review_decision_recorded"`.
- JSON output includes `review_task.status` as `approved`.
- SQLite contains a `review_decision_recorded` audit event for the run.

Use `--decision reject` to record a rejection. Researcher-role principals should receive `review_decision_not_authorized` and leave the task pending.

### 6. Export an Approved Report

```bash
python scripts/export_report_from_store.py --sqlite-db outputs/production.sqlite --output-dir outputs --review-id review-local-phase-output-run --user-id reviewer-1 --role reviewer --report-type research_report --report-output outputs/exported/research_report.md --exported-at 2026-06-15T00:06:00Z
```

Expected result:

- Command exits `0` after the review task is approved.
- JSON output has `"reason": "export_allowed"`.
- `outputs/exported/research_report.md` is written.
- SQLite contains `prompt_injection_decision_recorded`, `citation_policy_decision_recorded`, and `report_export_decision_recorded` audit events for the run.

If the review task is still pending, the command exits non-zero with `"reason": "review_required"` and does not write the report file.

### 7. Run Readiness Checks

```bash
python scripts/check_production_readiness.py --sqlite-db outputs/production.sqlite --artifact-manifest outputs/artifact_manifest.json --run-summary outputs/run_summary.json --run-id local-phase-output-run --tenant-id local_tenant --workspace-id local_workspace
```

Expected result:

- Command exits `0`.
- JSON output has `"status": "pass"`.
- Every check has `"passed": true`.
- SQLite contains a scoped `readiness_check_results` record for the run.
- The `review_approval_present` and `report_export_audit_present` checks pass only after the review task is approved and report export records an allowed decision.

### 8. Summarize Production Observability

```bash
python scripts/summarize_production_observability.py --sqlite-db outputs/production.sqlite --run-id local-phase-output-run --tenant-id local_tenant --workspace-id local_workspace
```

Expected result:

- Command exits `0` for the correct tenant/workspace scope.
- JSON output has `"status": "ok"` after readiness passes.
- JSON output includes `readiness.latest_status`, `review.status_counts`, `connectors.health_status_counts`, `connectors.validation_status_counts`, `report_export.allowed_count`, and `audit_events.event_type_counts`.
- If review approval, readiness, or allowed report export is missing, JSON output has `"status": "attention"` and machine-readable `attention_reasons`.

### 9. Run an Incident Recovery Drill

```bash
python scripts/run_incident_recovery_drill.py --sqlite-db outputs/production.sqlite --backup outputs/drill_production_backup.json --restored-sqlite-db outputs/drill_restored_production.sqlite --run-id local-phase-output-run --tenant-id local_tenant --workspace-id local_workspace
```

Expected result:

- Command exits `0` for the correct tenant/workspace scope.
- JSON output has `"status": "pass"` when backup counts match restored counts.
- JSON output includes `incident.detected`, `incident.attention_reasons`, `backup.counts`, `restore.counts`, `restore.counts_match_backup`, `restored_scope_inspection.inspectable`, and `restored_observability.status`.
- Wrong tenant/workspace scope exits non-zero before backup export.

Save the JSON output to `outputs/incident_recovery_drill.json` when building a compliance evidence bundle.

### 10. Build a Compliance Evidence Bundle

```bash
python scripts/build_compliance_evidence_bundle.py --sqlite-db outputs/production.sqlite --artifact-manifest outputs/artifact_manifest.json --source-registry config/source_registry.example.json --backup outputs/production_backup.json --drill-json outputs/incident_recovery_drill.json --output outputs/compliance_evidence_bundle.json --run-id local-phase-output-run --tenant-id local_tenant --workspace-id local_workspace
```

Expected result:

- Command exits `0` for the correct tenant/workspace scope.
- `outputs/compliance_evidence_bundle.json` exists.
- JSON output has `"status": "ready_for_pilot_review"` when required local evidence is present.
- JSON output includes `policy_documents`, `source_approval`, `readiness`, `review`, `report_export`, `observability`, `backup`, `incident_recovery_drill`, `attestations`, and `scoped_inspection`.
- Wrong tenant/workspace scope exits non-zero before writing the bundle.

### 11. Record a Compliance Attestation

```bash
python scripts/record_compliance_attestation.py --bundle outputs/compliance_evidence_bundle.json --attestations outputs/compliance_attestations.jsonl --run-id local-phase-output-run --tenant-id local_tenant --workspace-id local_workspace --approver-id privacy-owner --approver-role privacy_owner --decision approve --comment "Privacy evidence reviewed for pilot intake." --attested-at 2026-06-15T00:30:00Z
```

Expected result:

- Command exits `0` for a matching bundle scope.
- `outputs/compliance_attestations.jsonl` exists.
- JSON output includes `decision`, `approver_role`, `bundle_status`, and `bundle_sha256`.
- `approve` is accepted only when `outputs/compliance_evidence_bundle.json` has `"status": "ready_for_pilot_review"`.
- Wrong tenant/workspace scope exits non-zero before appending a record.

To include matching attestation counts in a later bundle output, add `--attestations outputs/compliance_attestations.jsonl` to the bundle command.

### 12. Build a Pilot Release Decision

```bash
python scripts/build_pilot_release_decision.py --bundle outputs/compliance_evidence_bundle.json --attestations outputs/compliance_attestations.jsonl --output outputs/pilot_release_decision.json --run-id local-phase-output-run --tenant-id local_tenant --workspace-id local_workspace --required-approver-role privacy_owner --required-approver-role security_owner --decided-at 2026-06-15T00:50:00Z
```

Expected result:

- Command exits `0` for a matching bundle scope.
- `outputs/pilot_release_decision.json` exists.
- JSON output has `"status": "approved_for_pilot"` when the bundle is ready and required latest approver attestations are approved.
- JSON output has `"status": "blocked"` with `blocking_reasons` such as `required_attestation_missing:security_owner` when required evidence is missing.
- Wrong tenant/workspace scope exits non-zero before writing the decision.

### 13. Export and Restore a Production Backup

```bash
python scripts/backup_production_store.py export --sqlite-db outputs/production.sqlite --backup outputs/production_backup.json
```

Expected result:

- Command exits `0`.
- `outputs/production_backup.json` exists.
- JSON output includes artifact manifest, evaluation run, evidence-memory/retrieval, evidence-grading methodology, external grading connector, connector health, staged connector validation, privacy approval, readiness check result, and audit event counts.
- If review tasks or reviewer methodology ratings are recorded for a run, JSON output also includes those counts.

Restore into a fresh SQLite file to verify recoverability:

```bash
python scripts/backup_production_store.py restore --backup outputs/production_backup.json --sqlite-db outputs/restored_production.sqlite
```

Expected result:

- Command exits `0`.
- `outputs/restored_production.sqlite` exists.
- JSON output reports restored artifact manifest, evaluation run, evidence-memory/retrieval, evidence-grading methodology, external grading connector, connector health, staged connector validation, privacy approval, readiness check result, and audit event counts.
- If review tasks or reviewer methodology ratings were present in the backup, JSON output also reports restored counts for them.

Inspect the restored database with the same scoped inspection command by replacing `outputs/production.sqlite` with `outputs/restored_production.sqlite`.

### 14. Run Automated Tests

```bash
python -m unittest discover
```

Expected result:

- All non-live tests pass.
- Live PubMed test remains skipped unless `VYU_RUN_LIVE_PUBMED_TESTS=1` is set.

## Readiness Checks

The readiness command currently validates:

| Check | Meaning |
| --- | --- |
| `scoped_manifest_access` | Manifest can be read with the provided tenant/workspace scope |
| `schema_version_current` | SQLite storage schema is on the expected production schema version |
| `migration_history_present` | Migration history includes the current production schema version |
| `approved_sources_present` | Manifest contains approved source records |
| `artifact_checksums_present` | Every artifact has a SHA-256 checksum |
| `artifact_checksums_match_files` | Manifest checksums match files on disk |
| `evaluation_run_present` | Evaluation evidence exists for the run |
| `audit_events_present` | Required production audit events exist |
| `review_approval_present` | A scoped review task is approved for the run |
| `report_export_audit_present` | An allowed report-export decision audit event exists for the run |
| `connector_health_present` | At least one passing connector health record exists for the run scope |
| `connector_validation_present` | At least one passing staged connector validation record exists for the run scope |
| `evidence_objects_present` | At least one scoped evidence object record exists |
| `retrieval_index_current` | The manifest index version has a matching scoped retrieval index record |
| `retrieval_run_present` | At least one scoped production retrieval run record exists |
| `research_memory_present` | At least one scoped production research-memory record exists |
| `evidence_methodology_run_present` | At least one scoped evidence methodology run record exists |
| `evidence_methodology_assessments_present` | Document-level scoped methodology assessment records exist |
| `evidence_methodology_scores_present` | Methodology assessments include reproducible evidence-strength and domain scores |
| `external_evidence_grading_connector_present` | At least one scoped external evidence-grading request/response record exists |
| `production_trust_score_present` | At least one scoped production Trust Score record exists |
| `production_trust_score_bounded` | Trust Score overall and component values are bounded and reproducible |
| `production_governance_box_present` | At least one scoped production Governance Box record exists |
| `production_governance_box_audit_export_status_present` | Governance Box records expose audit ID, review decision, and export status |
| `external_governance_connector_present` | At least one scoped external governance request/response record exists |
| `run_summary_consistent` | Machine-readable run summary matches the artifact manifest |
| `wrong_scope_rejected` | Incorrect tenant/workspace access is blocked |

## External Governance Connector Placeholders

The local phase-output workflow records an external governance request/response using placeholder configuration only. Replace these before live use:

- Provider endpoint: `https://governance.example.invalid/v1/evaluate-output`
- Webhook endpoint: `https://api.vyu.example.invalid/webhooks/governance`
- API token secret: `aws-secretsmanager:vyu/external-governance/api-token`
- Webhook signing secret: `aws-secretsmanager:vyu/external-governance/webhook-secret`

External governance payloads should remain scoped, auditable, signed, idempotent, and data-minimized. Passage text is excluded by default unless a live provider contract explicitly permits it.

## Failure Triage

### `schema_version_current`

Likely causes:

- SQLite database was created by an older version of the production storage adapter.
- The schema metadata table is missing or was manually edited.
- A future migration changed the expected schema version without updating the local database.

Recommended action:

1. Re-run artifact generation with `--sqlite-db outputs/production.sqlite`.
2. If the check still fails, export a backup before running any future migration or rebuild step.
3. Re-run readiness checks.

### `migration_history_present`

Likely causes:

- SQLite database was created before migration history tracking existed.
- The migration history table is missing or was manually edited.
- Schema metadata and migration history are from different database builds.

Recommended action:

1. Re-run artifact generation with `--sqlite-db outputs/production.sqlite`.
2. Export a fresh backup after readiness passes.
3. Re-run readiness checks.

### `scoped_manifest_access`

Likely causes:

- Wrong `--run-id`.
- Wrong `--tenant-id` or `--workspace-id`.
- SQLite database was not generated with `--sqlite-db`.
- Manifest was not saved to SQLite.

Recommended action:

1. Re-run artifact generation with `--sqlite-db outputs/production.sqlite`.
2. Inspect the database with the expected tenant/workspace scope.
3. Confirm the manifest uses `local_tenant` and `local_workspace` for local runs.

### `approved_sources_present`

Likely causes:

- Artifact generation was run without `--source-registry`.
- `config/source_registry.example.json` is missing `dummy_corpus` or `golden_questions`.
- Source records are not marked `approved`.
- Source records are missing `approved_by` or `approved_at`.

Recommended action:

1. Confirm the registry file contains approved source records.
2. Re-run artifact generation with `--source-registry config/source_registry.example.json`.
3. Re-run readiness checks.

### `artifact_checksums_present`

Likely causes:

- Artifact manifest was manually edited.
- Artifact generation did not complete.
- A custom artifact record was added without `checksum_sha256`.

Recommended action:

1. Re-run artifact generation.
2. Avoid manual manifest edits.
3. Re-run readiness checks.

### `artifact_checksums_match_files`

Likely causes:

- Output files changed after manifest generation.
- Artifacts were deleted.
- Manifest and output directory are from different runs.

Recommended action:

1. Re-run artifact generation.
2. Confirm `--artifact-manifest` points to the same `outputs/` directory.
3. Re-run readiness checks.

### `evaluation_run_present`

Likely causes:

- Evaluation registry was not written.
- SQLite persistence failed before saving the evaluation run.
- The stored evaluation record points to a different manifest path.

Recommended action:

1. Re-run artifact generation with `--sqlite-db`.
2. Inspect `outputs/evaluation/runs.jsonl`.
3. Inspect SQLite with `scripts/inspect_production_store.py`.

### `audit_events_present`

Likely causes:

- SQLite persistence was not enabled.
- Audit event insertion failed.
- The database was created by an older run before audit events were implemented.

Recommended action:

1. Re-run artifact generation with `--sqlite-db`.
2. Inspect the store and confirm the required event types exist:
   - `artifact_manifest_saved`
   - `evaluation_run_saved`
   - `phase_outputs_completed`
   - `evidence_object_recorded`
   - `retrieval_index_recorded`
   - `retrieval_run_recorded`
   - `production_research_memory_saved`
   - `evidence_methodology_assessment_recorded`
   - `evidence_methodology_run_recorded`
   - `external_evidence_grading_request_recorded`
   - `external_evidence_grading_response_recorded`
   - `review_task_created`
   - `review_decision_recorded`, after a reviewer decision is recorded
   - `report_export_decision_recorded`, after report export is attempted
   - `connector_health_recorded`
   - `connector_validation_recorded`


### `evidence_objects_present`, `retrieval_index_current`, `retrieval_run_present`, `research_memory_present`

Likely causes:

- Artifact generation was run with an older code path that did not persist evidence-memory/retrieval control-plane records.
- The manifest index version does not match the persisted retrieval index record.
- Retrieval was executed outside the requested tenant/workspace/user/topic scope.
- Production research memory was not saved after retrieval.

Recommended action:

1. Re-run artifact generation with `--sqlite-db`.
2. Inspect the store and confirm these arrays are populated:
   - `evidence_object_records`
   - `retrieval_index_records`
   - `retrieval_run_records`
   - `production_research_memory_records`
3. Confirm the manifest `index_version` matches one scoped retrieval index record.
4. Confirm all records use the expected tenant/workspace scope.

### `evidence_methodology_run_present`, `evidence_methodology_assessments_present`, `evidence_methodology_scores_present`, `external_evidence_grading_connector_present`

Likely causes:

- Artifact generation was run with an older code path that did not persist evidence-grading methodology records.
- External grading connector configuration is missing or the replay/live transport failed before a request/response was recorded.
- Methodology assessments were created outside the requested tenant/workspace scope.
- Assessment records are missing evidence-strength or domain score fields.

Recommended action:

1. Re-run artifact generation with `--sqlite-db`.
2. Inspect the store and confirm these arrays are populated:
   - `evidence_methodology_run_records`
   - `evidence_methodology_assessment_records`
   - `external_evidence_grading_request_records`
   - `external_evidence_grading_response_records`
3. Confirm document-level assessments have `evidence_strength_score`, `evidence_strength_band`, and `methodology_domain_scores`.
4. For live external providers, confirm endpoint URL, auth secret reference, webhook URL, and webhook signing secret are configured in the deployment environment.

### `review_approval_present`

Likely causes:

- The reviewer decision command was not run.
- The task was rejected instead of approved.
- The decision belongs to another tenant/workspace scope.

Recommended action:

1. Inspect the reviewer queue for the run.
2. Record an approved reviewer decision with `scripts/record_review_decision.py`.
3. Re-run readiness checks.

### `report_export_audit_present`

Likely causes:

- Report export was not attempted after approval.
- Report export was blocked by review, authorization, prompt-injection, or citation-policy gates.
- The export decision audit event belongs to another tenant/workspace scope.

Recommended action:

1. Run `scripts/export_report_from_store.py` after approval.
2. Inspect production audit events for an allowed `report_export_decision_recorded` event.
3. Re-run readiness checks.

### `connector_health_present`

Likely causes:

- SQLite persistence was not enabled.
- The database was created before connector health persistence was implemented.
- The stored connector health record failed or belongs to another tenant/workspace scope.

Recommended action:

1. Re-run artifact generation with `--sqlite-db`.
2. Inspect production audit events for `connector_health_recorded`.
3. Re-run readiness checks.

### `connector_validation_present`

Likely causes:

- SQLite persistence was not enabled.
- The database was created before staged connector validation persistence was implemented.
- The stored replay or live validation record failed or belongs to another tenant/workspace scope.

Recommended action:

1. Re-run artifact generation with `--sqlite-db`.
2. Inspect production audit events for `connector_validation_recorded`.
3. Re-run readiness checks.

### `run_summary_consistent`

Likely causes:

- `outputs/run_summary.json` is missing.
- Run summary and artifact manifest are from different runs.
- Artifact generation was interrupted.
- Manifest was manually edited after summary generation.

Recommended action:

1. Re-run artifact generation.
2. Confirm `outputs/run_summary.json` and `outputs/artifact_manifest.json` have the same run ID, corpus version, index version, artifact count, and source count.
3. Re-run readiness checks.

### `wrong_scope_rejected`

Likely causes:

- Scoped read methods were bypassed or changed.
- Tenant/workspace enforcement regressed.

Recommended action:

1. Run `python -m unittest tests.test_production_storage`.
2. Run `python -m unittest tests.test_check_production_readiness`.
3. Do not treat the run as production-ready until wrong-scope access is rejected.

## Live PubMed Validation

Normal local checks do not call PubMed. To run the gated live test in a configured environment:

```bash
set VYU_RUN_LIVE_PUBMED_TESTS=1
set VYU_NCBI_EMAIL=your-team-email@example.com
set VYU_NCBI_TOOL=vyu-poc
python -m unittest tests.test_pubmed_live_connector
```

Optional:

```bash
set VYU_NCBI_API_KEY=your-ncbi-api-key
```

Live PubMed validation should be run in staging, not as part of normal offline unit tests.

## Connector Health Validation

Replay connector validation can be exercised through the test suite:

```bash
python -m unittest tests.test_connector_health
```

Expected result:

- Command exits `0`.
- PubMed replay validation records status `ok`.
- Failing connector behavior is captured as a failed validation record rather than raising out of the health check.

## Evidence to Retain

For each pilot-style run, retain:

- `outputs/artifact_manifest.json`
- `outputs/run_summary.json`
- `outputs/production.sqlite`
- `outputs/production_backup.json`
- `outputs/evaluation/runs.jsonl`
- `outputs/phase5/governance_audit_record.json`
- Readiness check JSON output
- Persisted `readiness_check_results` records in `outputs/production.sqlite` and restored backups
- Reviewer queue inspection output from `scripts/inspect_review_queue.py`
- Reviewer decision output from `scripts/record_review_decision.py`
- Exported report file, such as `outputs/exported/research_report.md`
- Prompt-injection, citation-policy, and final report-export decision audit events for any report exports performed with production storage
- Incident/recovery drill output from `scripts/run_incident_recovery_drill.py`
- Compliance evidence bundle from `scripts/build_compliance_evidence_bundle.py`
- Compliance attestation JSONL from `scripts/record_compliance_attestation.py`
- Pilot release-decision output from `scripts/build_pilot_release_decision.py`
- Test output from `python -m unittest discover`

## Stop Conditions

Do not proceed to pilot-style review if:

- Readiness status is `fail`.
- Any tenant/workspace scope check fails.
- Any high-risk output lacks an approved human review task.
- Any artifact checksum is missing or mismatched.
- Approved source records are missing.
- Required audit events are missing.
- Backup export or restore fails.
- Required local approvers have not recorded compliance attestations for the reviewed bundle.
- Pilot release decision is not `approved_for_pilot`.
- Tests fail.
- The run includes live sources that are not approved in the source registry.
