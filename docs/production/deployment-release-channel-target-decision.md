# Deployment Release-Channel Target Decision Contract

The deployment release-channel target-decision module in `src/vyu/deployment/release_channel_target_decision.py`, backed by `scripts/decide_deployment_release_channel_target.py`, records a deterministic local operator decision for one abstract deployment target family from `outputs/deployment_release_channel_target_readiness.json`.

This module chooses only a target family such as `serverless_function`, `container_service`, or `managed_job_or_worker`. It does not select a provider, configure infrastructure, transfer artifacts, sign artifacts, upload to CI/CD, generate SBOMs, scan vulnerabilities, persist records to production storage, or deploy anything.

## Command

```bash
python scripts/decide_deployment_release_channel_target.py \
  --target-readiness outputs/deployment_release_channel_target_readiness.json \
  --decision choose \
  --target-family serverless_function \
  --operator-id target-operator \
  --operator-role deployment_operator \
  --rationale "Serverless function selected for provider planning." \
  --decided-at 2026-06-15T05:00:00Z \
  --output outputs/deployment_release_channel_target_decision.json
```

Use `--decision defer` without `--target-family` when target selection is intentionally postponed. Use `--decision block` without `--target-family` when an operator blocks target selection. Operators may override default next actions by passing one or more `--next-action` values.

## Output

The command writes `outputs/deployment_release_channel_target_decision.json` with:

1. schema version;
2. top-level status: `selected`, `deferred`, or `blocked`;
3. target-readiness path and SHA-256;
4. target-readiness schema, status, timestamp, and note name;
5. inherited package metadata;
6. inherited release-channel operator metadata;
7. target-decision operator ID and role;
8. target-decision value;
9. selected abstract target family, when `decision.value` is `choose`;
10. operator rationale;
11. target-selection scope;
12. candidate target families;
13. selected target provider, which remains `null`;
14. provider configuration, which remains `{}`;
15. export-summary hash evidence;
16. release-channel evidence hashes and counts;
17. local-only limits;
18. inherited handoff checklist;
19. next actions;
20. blocking reasons;
21. check summary, including `next_action_count`;
22. individual checks.

## Checks

The decision record verifies:

- `target_readiness_file_readable`
- `target_readiness_json_valid`
- `target_readiness_schema_supported`
- `target_readiness_status_ready`
- `target_readiness_checks_passed`
- `target_readiness_blocking_reasons_absent`
- `target_family_candidates_present`
- `decision_supported`
- `operator_metadata_present`
- `choose_requires_ready_readiness`
- `choose_requires_candidate_target_family`
- `block_or_defer_requires_no_selected_target_family`
- `target_selection_scope_local_only`
- `no_target_provider_selected`
- `no_provider_configuration_recorded`
- `export_summary_sha256_present`
- `evidence_index_sha256_present`
- `package_metadata_present`
- `local_only_limits_present`
- `handoff_checklist_present`
- `next_actions_present`

## Status behavior

`decision.value = choose` produces `status = selected` only when all checks pass and the chosen target family exists in `candidate_target_families`.

`decision.value = defer` produces `status = deferred` only when all checks pass and no target family is selected.

`decision.value = block` always produces `status = blocked` and records `operator_decision_block` in `blocking_reasons`.

Any failed check produces `status = blocked` for choose/block decisions and blocks deferred records as well.

## Relationship to target readiness

The decision record consumes the target-readiness note produced by:

```bash
python scripts/build_deployment_release_channel_target_readiness.py \
  --export-summary outputs/deployment_release_channel_export_summary.json \
  --readiness-name local-release-channel-target-readiness \
  --created-at 2026-06-15T04:45:00Z \
  --output outputs/deployment_release_channel_target_readiness.json
```

The decision record binds to that note by path and SHA-256. It inherits package metadata, release-channel operator metadata, export-summary hash evidence, evidence hashes, evidence counts, local-only limits, and the handoff checklist from the readiness note.

## Limits

This module intentionally remains a local decision record. It does not:

- choose AWS, Azure, Google Cloud, Kubernetes, or any other provider;
- write provider configuration;
- create IAM, networking, Terraform, Docker, OIDC/JWKS, CORS/WAF, or rate-limit resources;
- upload or transfer artifacts;
- sign artifacts or call KMS;
- run CI/CD;
- generate SBOMs;
- run vulnerability scans;
- persist the decision to production storage;
- deploy infrastructure.

## Next boundary

The follow-on deployment module is the local release-channel provider-planning preflight in `docs/production/deployment-release-channel-provider-preflight.md`, which consumes `outputs/deployment_release_channel_target_decision.json`. It still avoids provider credentials, cloud mutation, artifact transfer, signing, CI/CD upload, SBOM generation, vulnerability scanning, and production persistence unless those boundaries are selected explicitly.
