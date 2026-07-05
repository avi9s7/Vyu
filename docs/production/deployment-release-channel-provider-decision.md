# Release-Channel Provider-Planning Decision Record Contract

The deployment release-channel provider-planning decision module in `src/vyu/deployment/release_channel_provider_decision.py`, backed by `scripts/decide_deployment_release_channel_provider.py`, records a deterministic local operator decision from `outputs/deployment_release_channel_provider_preflight.json`.

This is a planning-control boundary only. It lets an operator approve, block, or defer the next provider-planning step while preserving the preflight guarantee that no concrete provider, credentials, provider configuration, cloud mutation, transfer, signing, CI/CD upload, SBOM generation, vulnerability scanning, production persistence, or deployment is introduced in this module.

## Command

```bash
python scripts/decide_deployment_release_channel_provider.py \
  --provider-preflight outputs/deployment_release_channel_provider_preflight.json \
  --decision proceed \
  --planning-track serverless_provider_requirements_review \
  --operator-id provider-operator \
  --operator-role deployment_operator \
  --rationale "Provider planning approved from local preflight." \
  --decided-at 2026-06-15T06:00:00Z \
  --output outputs/deployment_release_channel_provider_decision.json
```

## Output

The command writes `outputs/deployment_release_channel_provider_decision.json` with:

1. schema version;
2. top-level status: `approved`, `deferred`, or `blocked`;
3. deterministic decision ID;
4. decision timestamp;
5. provider-preflight path and SHA-256;
6. provider-preflight status and schema version;
7. package metadata;
8. target-decision, target-operator, inherited-operator, and provider-decision operator metadata;
9. decision value and rationale;
10. abstract provider-planning track;
11. local planning-decision scope;
12. selected abstract target family;
13. explicit absence of selected provider and provider configuration;
14. target-selection scope;
15. candidate target families;
16. export-summary and evidence-hash metadata;
17. evidence counts;
18. local-only limits;
19. handoff checklist;
20. provider-planning requirements;
21. next actions;
22. blocking reasons;
23. summary counts, including `next_action_count`;
24. named checks.

Expected output for an approved local provider-planning decision:

```json
{
  "schema_version": 1,
  "status": "approved",
  "provider_preflight": {
    "status": "ready",
    "sha256": "..."
  },
  "decision": {
    "value": "proceed",
    "provider_planning_track": "serverless_provider_requirements_review",
    "rationale": "Provider planning approved from local preflight."
  },
  "planning_decision_scope": "local_provider_planning_decision_only",
  "selected_target_provider": null,
  "provider_configuration": {},
  "blocking_reasons": []
}
```

## Checks

An `approved` provider-planning decision requires all checks to pass:

- `provider_preflight_file_readable`
- `provider_preflight_json_valid`
- `provider_preflight_schema_supported`
- `provider_preflight_status_ready`
- `provider_preflight_checks_passed`
- `provider_preflight_blocking_reasons_absent`
- `decision_supported`
- `operator_metadata_present`
- `proceed_requires_ready_preflight`
- `proceed_requires_provider_planning_track`
- `block_or_defer_requires_no_provider_planning_track`
- `selected_target_family_present`
- `planning_scope_preflight_only`
- `target_selection_scope_local_only`
- `no_target_provider_selected`
- `no_provider_configuration_recorded`
- `export_summary_sha256_present`
- `evidence_index_sha256_present`
- `package_metadata_present`
- `target_operator_metadata_present`
- `local_only_limits_present`
- `handoff_checklist_present`
- `planning_requirements_present`
- `next_actions_present`

## Blocking behavior

The decision is `blocked` when:

- the provider-preflight file is missing or not valid JSON;
- the provider-preflight schema version is unsupported;
- the provider-preflight status is not `ready`;
- any provider-preflight check failed;
- provider-preflight blocking reasons are present;
- the operator decision is unsupported;
- operator ID, operator role, or rationale is missing;
- `proceed` is requested without an abstract provider-planning track;
- `block` or `defer` is recorded with a planning track;
- the selected target family is missing;
- the preflight scope is not provider-planning-preflight-only;
- target-selection scope is not local-only;
- a concrete provider is already selected;
- provider configuration is already recorded;
- required hash evidence, package metadata, target-operator metadata, local-only limits, handoff checklist, planning requirements, or next actions are absent.

## Relationship to provider preflight

The decision consumes the provider preflight created by:

```bash
python scripts/build_deployment_release_channel_provider_preflight.py \
  --target-decision outputs/deployment_release_channel_target_decision.json \
  --preflight-name local-release-channel-provider-planning-preflight \
  --created-at 2026-06-15T05:30:00Z \
  --output outputs/deployment_release_channel_provider_preflight.json
```

The decision binds to that preflight by path and SHA-256. It inherits package metadata, target-decision metadata, target operator metadata, release-channel operator metadata, evidence hashes, evidence counts, local-only limits, handoff checklist items, and provider-planning requirements.

## Limits

This module intentionally remains local and provider-agnostic. It does not:

- choose a concrete provider;
- record provider credentials;
- write provider configuration;
- create IAM, networking, Terraform, Docker, OIDC/JWKS, CORS/WAF, rate-limit, or runtime infrastructure;
- execute shell commands;
- upload or transfer artifacts;
- sign artifacts or call KMS;
- run CI/CD;
- generate SBOMs;
- run vulnerability scans;
- persist the decision to production storage;
- deploy infrastructure.

## Next boundary

The next deployment module can add a local provider-plan draft checklist that consumes `outputs/deployment_release_channel_provider_decision.json`, while still avoiding provider credentials, cloud mutation, artifact transfer, signing, CI/CD upload, SBOM generation, vulnerability scanning, and production persistence unless those boundaries are selected explicitly.
