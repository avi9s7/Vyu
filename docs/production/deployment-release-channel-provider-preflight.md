# Deployment Release-Channel Provider-Planning Preflight Contract

The deployment release-channel provider-planning preflight module in `src/vyu/deployment/release_channel_provider_preflight.py`, backed by `scripts/build_deployment_release_channel_provider_preflight.py`, builds a deterministic local JSON preflight from `outputs/deployment_release_channel_target_decision.json`.

This module verifies that an abstract target-family decision is selected and ready for later provider-specific planning. It does not choose AWS, Azure, Google Cloud, Kubernetes, or any other provider; does not write provider configuration; does not transfer artifacts; does not sign artifacts; does not upload to CI/CD; does not generate SBOMs; does not scan vulnerabilities; does not persist records to production storage; and does not deploy anything.

## Command

```bash
python scripts/build_deployment_release_channel_provider_preflight.py \
  --target-decision outputs/deployment_release_channel_target_decision.json \
  --preflight-name local-release-channel-provider-planning-preflight \
  --created-at 2026-06-15T05:30:00Z \
  --output outputs/deployment_release_channel_provider_preflight.json
```

Operators may override the default abstract provider-planning requirements by passing one or more `--planning-requirement` values. Operators may override default next actions by passing one or more `--next-action` values.

## Output

The command writes `outputs/deployment_release_channel_provider_preflight.json` with:

1. schema version;
2. top-level `ready` or `blocked` status;
3. preflight name;
4. target-decision path and SHA-256;
5. target-decision schema, status, timestamp, and decision ID;
6. provider-planning preflight scope;
7. selected abstract target family;
8. null selected target provider;
9. empty provider configuration;
10. package metadata;
11. target-decision operator metadata;
12. inherited release-channel operator metadata;
13. target decision payload;
14. target-selection scope;
15. candidate target families;
16. export-summary hash evidence;
17. evidence hashes and counts;
18. local-only limits;
19. handoff checklist;
20. provider-planning requirements;
21. next actions;
22. blocking reasons;
23. check summary, including `planning_requirement_count`;
24. individual checks.

Expected output for a ready local provider-planning preflight:

```json
{
  "schema_version": 1,
  "status": "ready",
  "preflight_name": "local-release-channel-provider-planning-preflight",
  "planning_scope": "provider_planning_preflight_only",
  "selected_target_family": "serverless_function",
  "selected_target_provider": null,
  "provider_configuration": {},
  "blocking_reasons": []
}
```

## Checks

A `ready` provider-planning preflight requires all checks to pass:

- `target_decision_file_readable`
- `target_decision_json_valid`
- `target_decision_schema_supported`
- `target_decision_status_selected`
- `target_decision_checks_passed`
- `target_decision_blocking_reasons_absent`
- `decision_value_choose`
- `selected_target_family_present`
- `selected_target_family_in_candidates`
- `target_selection_scope_local_only`
- `no_target_provider_selected`
- `no_provider_configuration_recorded`
- `export_summary_sha256_present`
- `evidence_index_sha256_present`
- `package_metadata_present`
- `target_operator_metadata_present`
- `local_only_limits_present`
- `handoff_checklist_present`
- `planning_requirements_recorded`
- `next_actions_present`

## Blocking behavior

The preflight is `blocked` when:

- the target-decision file is missing or not valid JSON;
- the target-decision schema version is unsupported;
- the target-decision status is not `selected`;
- any target-decision check failed;
- target-decision blocking reasons are present;
- `decision.value` is not `choose`;
- the selected target family is missing or not listed in `candidate_target_families`;
- a target provider is already selected;
- provider configuration is already recorded;
- target-selection scope is not local-only;
- required hash evidence, package metadata, local-only limits, handoff checklist, planning requirements, or next actions are absent.

## Relationship to target decision

The preflight consumes the target decision created by:

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

The preflight binds to that decision by path and SHA-256. It inherits package metadata, target-decision operator metadata, release-channel operator metadata, evidence hashes, evidence counts, local-only limits, and handoff checklist items.

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
- persist the preflight to production storage;
- deploy infrastructure.

## Next boundary

The next deployment module can add a local provider-planning decision record that consumes `outputs/deployment_release_channel_provider_preflight.json`, while still avoiding provider credentials, cloud mutation, artifact transfer, signing, CI/CD upload, SBOM generation, vulnerability scanning, and production persistence unless those boundaries are selected explicitly.
