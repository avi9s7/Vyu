# Deployment Command Transcript Evidence

## Transcript Contract

The deployment command transcript module writes deterministic local JSON evidence from explicitly supplied command-result metadata. It is intended to capture what a packaging or release command reported without letting this module run arbitrary shell commands.

Implemented files:

- `src/vyu/deployment/command_transcript.py`
- `scripts/write_deployment_command_transcript.py`
- `tests/test_deployment_command_transcript.py`

The transcript evidence is a local provenance aid for package/release rehearsals. It does not execute commands, choose a CI vendor, sign artifacts, or deploy infrastructure.

## Transcript Behavior

`build_deployment_command_transcript(...)` records:

1. command array;
2. intended purpose;
3. exit code;
4. derived status `passed` or `failed`;
5. explicit started-at and finished-at timestamps;
6. stdout SHA-256, byte length, bounded excerpt, and truncation flag;
7. stderr SHA-256, byte length, bounded excerpt, and truncation flag;
8. output artifact paths with existence, size, and SHA-256 when present.

The top-level JSON includes:

- `schema_version`
- `status`
- `purpose`
- `command`
- `exit_code`
- `started_at`
- `finished_at`
- `outputs.stdout.sha256`
- `outputs.stdout.excerpt`
- `outputs.stdout.truncated`
- `outputs.stderr.sha256`
- `outputs.stderr.excerpt`
- `outputs.stderr.truncated`
- `artifacts[].path`
- `artifacts[].exists`
- `artifacts[].size_bytes`
- `artifacts[].sha256`
- `summary`

## Operator Command

Write transcript evidence from explicit metadata:

```bash
python scripts/write_deployment_command_transcript.py \
  --command-json '["python", "scripts/check_deployment_release_package.py"]' \
  --purpose "check deployment release package" \
  --exit-code 0 \
  --started-at 2026-06-15T01:14:00Z \
  --finished-at 2026-06-15T01:14:03Z \
  --stdout-file outputs/release_check_stdout.txt \
  --stderr-file outputs/release_check_stderr.txt \
  --artifact outputs/deployment_release_package_checklist.json \
  --output outputs/deployment_command_transcript.json
```

For short rehearsals, stdout/stderr can be supplied inline:

```bash
python scripts/write_deployment_command_transcript.py \
  --command-json '["python", "scripts/validate_deployment_package.py", "--manifest", "deploy/serverless/package.manifest.json"]' \
  --purpose "validate deployment package manifest" \
  --exit-code 0 \
  --started-at 2026-06-15T01:15:00Z \
  --finished-at 2026-06-15T01:15:01Z \
  --stdout-text '{"status":"pass"}' \
  --stderr-text '' \
  --output outputs/deployment_command_transcript.json
```

Expected output status for exit code `0`:

```json
{
  "status": "passed"
}
```

Expected output status for a non-zero exit code:

```json
{
  "status": "failed"
}
```

The command exits with status code `0` for passed transcripts, `1` for failed transcripts, and `2` for malformed transcript metadata.

## Safety Boundaries

- This module does not run shell commands.
- It only consumes explicit command-result metadata or pre-captured stdout/stderr text files.
- Operators should not include secrets in stdout/stderr text.
- Stored stdout/stderr are bounded excerpts plus SHA-256 digests, not full unbounded logs.
- Artifact summaries include path, existence, size, and SHA-256 only.

## Relationship to Earlier Deployment Modules

```text
scripts/write_deployment_command_transcript.py
  -> DeploymentCommandTranscript
    -> pre-captured command metadata
    -> optional local artifact summaries
```

This module can record transcript evidence for commands such as:

- `scripts/validate_deployment_package.py`
- `scripts/plan_deployment_package.py`
- `scripts/build_deployment_archive.py`
- `scripts/write_deployment_package_evidence.py`
- `scripts/check_deployment_release_package.py`
- `scripts/smoke_test_deployment.py`

It does not yet make the release-package checklist consume transcript evidence; that can be a follow-on module.

## Current Limits

- Local JSON transcript evidence only.
- No arbitrary shell execution.
- No CI vendor integration.
- No KMS, signing, Sigstore, SLSA attestation, SBOM, vulnerability scanning, Docker, Terraform, IAM, OIDC/JWKS, cloud deployment, CORS/WAF, or rate-limit configuration.

## Next Module Boundary

The next deployment module can add a transcript bundle/checker that groups multiple command transcripts and verifies the release-package command sequence, without running commands or integrating with a CI vendor.
