# AWS deployment runbook

Operator runbook for promoting a reviewed Terraform plan and immutable container images into a VYU AWS environment (`dev`, `staging`, or `prod`).

## Scope

This runbook covers:

- Prerequisites and identity verification
- Secret presence checks
- Plan review and artifact binding
- Database migration
- ECS service promotion
- Post-deploy smoke and dashboard checks
- Release evidence capture
- Abort conditions

It complements:

- `.github/workflows/infra-plan.yml` — pull-request Terraform plan
- `.github/workflows/deploy.yml` — protected-environment apply
- `scripts/deploy_smoke.py` — HTTPS smoke checks
- `scripts/configure_secrets.py` — Secrets Manager updates

## Prerequisites

Before starting, confirm:

| Check | Command / location |
| --- | --- |
| GitHub environment exists and is protected for `staging` / `prod` | Repository **Settings → Environments** |
| OIDC role ARNs configured | Repository variables: `AWS_PLAN_ROLE_ARN`, `AWS_APPLY_ROLE_ARN`, `AWS_BUILD_ROLE_ARN` |
| Network variables configured | `AWS_PRIVATE_SUBNET_IDS`, `AWS_MIGRATION_SECURITY_GROUP_ID`, `APP_BASE_URL` |
| Operator has environment approval rights | GitHub environment reviewers |
| No open critical alarms | CloudWatch alarm `vyu-{env}-*` in `ALARM` state |
| Change ticket / release record opened | Internal change system |

Record the operator name, UTC timestamp, target environment, and source commit SHA before any write action.

## 1. Verify operator identity

1. Sign in to GitHub with your corporate account.
2. Confirm you are listed as a required reviewer for the target environment.
3. Assume only the AWS access path provided by GitHub OIDC. Do not use long-lived access keys.
4. For manual AWS CLI steps, configure a short-lived session through the approved break-glass role only when the deploy workflow is unavailable.

## 2. Verify secret presence

Application secrets are stored in AWS Secrets Manager and tagged with `Environment={env}`.

Required containers:

| Secret name | Purpose |
| --- | --- |
| `vyu/{env}/database/connection` | Application database connectivity |
| `vyu/{env}/providers` | External provider credentials |

Verify each secret exists and has a current version:

```powershell
aws secretsmanager describe-secret --secret-id "vyu/staging/database/connection"
aws secretsmanager describe-secret --secret-id "vyu/staging/providers"
```

Abort if:

- A required secret is missing
- The `Environment` tag does not match the target environment
- A secret has no `AWSCURRENT` version

Do not print secret values in tickets, chat, or CI logs.

## 3. Review the Terraform plan

### Pull request plan

1. Open or update the infrastructure pull request.
2. Wait for **Infra Plan** workflow success.
3. Download artifacts:
   - `terraform-plan-{commit_sha}`
   - `terraform-plan-metadata-{commit_sha}`
4. Review the plan output for:
   - Unexpected destructive changes
   - Public exposure changes
   - IAM broadening
   - Database replacement
   - Image digest updates for `web`, `api`, and `worker`

### Abort conditions before apply

Stop and escalate if the plan:

- Replaces the RDS instance without an approved maintenance window
- Opens security groups to `0.0.0.0/0`
- Deletes audit, evidence, or state resources
- Changes production WAF or Cognito settings without security review
- Does not match the reviewed commit SHA

## 4. Run the deploy workflow

Trigger **Deploy** manually with:

| Input | Value |
| --- | --- |
| `environment` | `dev`, `staging`, or `prod` |
| `commit_sha` | Exact SHA from the reviewed plan metadata |
| `plan_artifact_name` | `terraform-plan-{commit_sha}` |

The workflow performs, in order:

1. Plan metadata verification
2. Immutable image build, vulnerability scan, push, and digest capture
3. ECS migration task execution and exit-code gate
4. `terraform apply` of the reviewed plan artifact
5. HTTPS smoke probes
6. Automatic ECS rollback evidence capture on smoke failure

Production requires GitHub environment owner approval before AWS write roles are assumed.

## 5. Database migration

The deploy workflow runs the `vyu-{env}-migration` ECS task before service promotion.

Manual verification when needed:

```powershell
aws ecs list-tasks --cluster "vyu-staging" --family "vyu-staging-migration" --desired-status STOPPED
aws ecs describe-tasks --cluster "vyu-staging" --tasks <task-arn>
```

Abort if:

- Migration container `exitCode` is not `0`
- Alembic revision in `/v1/version` does not match the expected revision after apply

Do not continue service promotion on a failed migration. Use the rollback runbook and database forward-fix guidance.

## 6. Service deploy evidence

After apply, capture:

| Field | Source |
| --- | --- |
| Commit SHA | Deploy workflow input |
| Image digests | `image-digests-{commit_sha}` artifact |
| Terraform apply ID | Workflow logs / Terraform output |
| ECS deployment IDs | `aws ecs describe-services --cluster vyu-{env} --services vyu-{env}-web vyu-{env}-api vyu-{env}-worker` |
| Migration task ARN | ECS `run-task` output |

## 7. Post-deploy smoke

Run the operator smoke script from a trusted workstation with a short-lived Cognito bearer token.

```powershell
$env:VYU_DEPLOY_SMOKE_BEARER_TOKEN = "<short-lived bearer token>"
uv run python scripts/deploy_smoke.py `
  --base-url "https://staging.example.com" `
  --expected-git-sha "<commit-sha>" `
  --expected-schema-revision "<alembic-revision>"
```

The script verifies:

- HTTPS-only origin
- `/v1/health/live` and `/v1/health/ready`
- `/v1/version` without sensitive fields
- Unauthenticated rejection on protected routes
- Authenticated `/v1/me`
- Idempotent `POST /v1/research/searches`
- Search detail and event visibility
- Required edge security headers

The script never prints the bearer token. Store only the JSON result in release evidence.

## 8. Dashboard and alarm checks

Open the CloudWatch dashboard `vyu-{env}-operations` and confirm:

- ALB `5xx` and latency panels are nominal
- ECS CPU/memory for `web`, `api`, and `worker` are stable
- RDS connections, storage, and latency are nominal
- SQS queue depth / age and DLQ message count are zero or expected
- Cognito auth failure and WAF block panels have not spiked

Confirm no critical SNS alarm is active:

```powershell
aws cloudwatch describe-alarms --alarm-name-prefix "vyu-staging-" --state-value ALARM
```

## 9. Release evidence template

Attach the following to the release record:

```json
{
  "environment": "staging",
  "operator": "<name>",
  "started_at_utc": "<iso8601>",
  "finished_at_utc": "<iso8601>",
  "commit_sha": "<git-sha>",
  "image_digests": {
    "web": "sha256:...",
    "api": "sha256:...",
    "worker": "sha256:..."
  },
  "terraform_plan_artifact": "terraform-plan-<git-sha>",
  "terraform_apply_id": "<apply-id>",
  "migration_task_arn": "<task-arn>",
  "migration_revision": "<alembic-revision>",
  "ecs_deployment_ids": {
    "web": "<deployment-id>",
    "api": "<deployment-id>",
    "worker": "<deployment-id>"
  },
  "smoke_status": "pass",
  "alarm_state": "OK",
  "notes": ""
}
```

## 10. Abort conditions during deploy

Halt the release immediately if any of the following occur:

- GitHub environment approval is denied
- Migration task fails or times out
- Terraform apply errors
- Smoke checks fail
- Critical alarm enters `ALARM`
- Unexpected Cognito login failures are reported during the change window

After abort:

1. Preserve workflow artifacts and ECS/Terraform logs
2. Follow `rollback.md` if services were promoted
3. Record the incident in the audit system with operator name and timestamps
