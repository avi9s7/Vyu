# Deployment Transcript Bundle Checker

## Bundle Contract

The deployment transcript bundle checker groups pre-written deployment command transcripts and verifies that the local package/release command sequence is represented by passed transcript evidence. It is a local release-readiness aid and does not execute commands, call a CI vendor, sign artifacts, or deploy infrastructure.

Implemented files:

- `src/vyu/deployment/transcript_bundle.py`
- `scripts/check_deployment_transcript_bundle.py`
- `tests/test_deployment_transcript_bundle.py`

The checker consumes the existing package manifest and one or more transcript JSON files written by `scripts/write_deployment_command_transcript.py`.

## Bundle Behavior

`build_deployment_transcript_bundle(...)` records:

1. deployment manifest path;
2. supplied transcript paths;
3. required validation commands from the manifest;
4. per-command coverage by passed transcript;
5. per-transcript schema, status, command, exit code, timestamps, output-hash, and artifact checks;
6. command sequence order based on the supplied transcript list;
7. top-level status `ready` or `blocked`.

A bundle is `ready` only when:

- at least one transcript is supplied;
- every supplied transcript is readable, schema-supported, passed, and has exit code `0`;
- each transcript includes valid stdout/stderr SHA-256 evidence;
- every recorded artifact exists and has SHA-256 evidence when marked present;
- every command in `required_validation_commands` has a passed transcript;
- the supplied transcript list follows the manifest command order.

The top-level JSON includes:

- `schema_version`
- `status`
- `created_at`
- `manifest_path`
- `transcript_paths`
- `required_commands[].covered`
- `required_commands[].transcript_path`
- `command_coverage`
- `transcripts[].artifact_summary`
- `checks[].name`
- `required_command_coverage_complete`
- `required_command_sequence_order`
- `checks[].passed`
- `summary.covered_command_count`

## Operator Command

Check a local bundle of command transcripts:

```bash
python scripts/check_deployment_transcript_bundle.py \
  --manifest deploy/serverless/package.manifest.json \
  --transcript outputs/transcripts/validate_deployment_config.json \
  --transcript outputs/transcripts/validate_deployment_package.json \
  --transcript outputs/transcripts/plan_deployment_package.json \
  --transcript outputs/transcripts/build_deployment_archive.json \
  --transcript outputs/transcripts/write_deployment_package_evidence.json \
  --transcript outputs/transcripts/check_deployment_release_package.json \
  --transcript outputs/transcripts/smoke_test_deployment.json \
  --output outputs/deployment_transcript_bundle.json
```

Use `--created-at` for deterministic rehearsals:

```bash
python scripts/check_deployment_transcript_bundle.py \
  --manifest deploy/serverless/package.manifest.json \
  --transcript outputs/transcripts/validate_deployment_config.json \
  --transcript outputs/transcripts/validate_deployment_package.json \
  --transcript outputs/transcripts/plan_deployment_package.json \
  --transcript outputs/transcripts/build_deployment_archive.json \
  --transcript outputs/transcripts/write_deployment_package_evidence.json \
  --transcript outputs/transcripts/check_deployment_release_package.json \
  --transcript outputs/transcripts/smoke_test_deployment.json \
  --created-at 2026-06-15T02:20:00Z \
  --output outputs/deployment_transcript_bundle.json
```

Expected output when every required command is covered in order:

```json
{
  "status": "ready"
}
```

Expected output when evidence is incomplete or out of order:

```json
{
  "status": "blocked"
}
```

The command exits with status code `0` for ready bundles, `1` for blocked bundles, and `2` for malformed bundle metadata or write errors.

## Safety Boundaries

- This module does not execute shell commands.
- It only reads local manifest and transcript JSON files.
- It does not validate real OIDC/JWKS identity providers.
- It does not configure cloud infrastructure, IAM, rate limits, WAF, CORS, Docker, Terraform, or CI providers.
- It does not sign artifacts or produce SLSA/Sigstore attestations.

## Relationship to Earlier Deployment Modules

```text
scripts/check_deployment_transcript_bundle.py
  -> DeploymentTranscriptBundle
    -> deploy/serverless/package.manifest.json
    -> outputs/transcripts/*.json from scripts/write_deployment_command_transcript.py
```

The bundle checker is intentionally separate from the release-package checklist. The release-package checklist validates package artifacts and evidence hashes. The transcript bundle validates that the local command sequence itself has passed transcript evidence.

## Current Limits

- Local JSON bundle only.
- Exact command-array matching against the manifest.
- Sequence order is based on the supplied transcript path order, not a CI timeline.
- No arbitrary shell execution.
- No CI vendor integration.
- No KMS, signing, Sigstore, SLSA attestation, SBOM, vulnerability scanning, Docker, Terraform, IAM, OIDC/JWKS, cloud deployment, CORS/WAF, or rate-limit configuration.

## Next Module Boundary

The next deployment module can add a local deployment release evidence summary that combines package evidence, release checklist output, and transcript bundle output into one operator review record, without signing, executing commands, or integrating with a CI/cloud provider.
