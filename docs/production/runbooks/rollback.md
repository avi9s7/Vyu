# AWS rollback runbook

Operator runbook for recovering from a failed deployment or bad release in VYU AWS environments.

## Rollback types

| Type | When to use | Primary action |
| --- | --- | --- |
| Application rollback | Bad container image or ECS task definition, database schema unchanged | Revert ECS services to the last known-good task definition revision |
| Infrastructure rollback | Bad Terraform change with a reviewed prior plan | Re-apply the previous reviewed Terraform plan artifact |
| Database forward-fix | Failed or partial migration, incompatible schema/data state | Apply a corrective forward migration; do not restore production DB in place |

Choose one primary path per incident. Mixing paths without coordination can leave services on a new schema with old application code.

## 1. Application rollback (ECS)

Use this when:

- Smoke checks fail after service promotion
- Error rate or latency alarms spike immediately after deploy
- The database migration succeeded and schema revision is correct

### 1.1 Identify the last known-good task definition

```powershell
$env = "staging"
$service = "vyu-$env-api"
aws ecs describe-services --cluster "vyu-$env" --services $service `
  --query "services[0].deployments" --output table
```

Record:

- Current task definition ARN
- Previous stable task definition ARN
- Active deployment ID

### 1.2 Verify image digests

Confirm the rollback target images match the prior release evidence:

```powershell
aws ecs describe-task-definition --task-definition "vyu-staging-api:<revision>" `
  --query "taskDefinition.containerDefinitions[0].image"
```

The image reference must be an immutable digest (`@sha256:...`) or a tag bound to the prior release record.

### 1.3 Roll back ECS services

Preferred automated path:

- Re-run the failed deploy workflow rollback job evidence, or
- Use the deploy workflow rollback step output artifact `rollback-evidence-{commit_sha}`

Manual rollback for each service (`web`, `api`, `worker`):

```powershell
$env = "staging"
$revision = "<known-good-revision>"
foreach ($service in @("web", "api", "worker")) {
  aws ecs update-service `
    --cluster "vyu-$env" `
    --service "vyu-$env-$service" `
    --task-definition "vyu-$env-$service:$revision" `
    --force-new-deployment
}
```

Wait for steady state:

```powershell
aws ecs wait services-stable --cluster "vyu-$env" --services "vyu-$env-web" "vyu-$env-api" "vyu-$env-worker"
```

### 1.4 Post-rollback smoke

```powershell
$env:VYU_DEPLOY_SMOKE_BEARER_TOKEN = "<short-lived bearer token>"
uv run python scripts/deploy_smoke.py `
  --base-url "https://staging.example.com" `
  --expected-schema-revision "<known-good-alembic-revision>" `
  --expected-image-digest "<known-good-api-digest>"
```

Abort further promotion if smoke does not pass after rollback.

## 2. Infrastructure rollback (Terraform)

Use this when:

- Terraform apply introduced an infrastructure defect
- The prior environment state is known-good and has a reviewed plan artifact

Steps:

1. Identify the last successful `commit_sha` and `terraform-plan-{commit_sha}` artifact.
2. Trigger **Deploy** with that exact commit SHA and plan artifact.
3. If the current state is unsafe, stop application traffic at the edge only after operator approval.
4. Re-apply the prior reviewed plan. Do not run `terraform apply` without the matching artifact.
5. Re-run migration only if the prior release requires it. If schema is already at the target revision, skip re-migration.

Do not use `terraform destroy` as a rollback mechanism for production.

## 3. Database forward-fix

Use this when:

- A migration failed partway through
- Application rollback alone would leave schema and code incompatible
- Data repair is required before services can resume

Escalation path:

1. Stop write traffic if data correctness is uncertain.
2. Open a database incident with DBA / platform owner approval.
3. Inspect migration task logs in CloudWatch log group `/vyu/{env}/migration`.
4. Author a forward-fix migration or one-off repair script.
5. Run the migration task in isolation and verify `schema_revision` via `/v1/version`.
6. Promote application services only after schema and smoke checks pass.

Do not downgrade Alembic revisions in production. Do not restore the live RDS instance from backup inside this rollback path; use `database-restore.md` for restore drills and disaster recovery.

## 4. Incident and audit record

For every rollback, record:

| Field | Example |
| --- | --- |
| Incident ID | `INC-2026-00042` |
| Operator | `<name>` |
| Environment | `staging` |
| Trigger | `smoke_failure`, `alarm`, `manual` |
| Bad commit SHA | `abc123...` |
| Restored task definition revisions | `web:12 api:12 worker:12` |
| Image digests restored | `sha256:...` |
| Migration revision before / after | `0008 / 0008` |
| Smoke result after rollback | `pass` |
| Alarm state after rollback | `OK` |
| Customer impact summary | `<text>` |

Attach:

- Deploy / rollback workflow artifacts
- `deploy_smoke.py` JSON output
- Relevant CloudWatch alarm history
- Terraform apply log excerpt

## 5. Decision guide

```text
Smoke failed, migration succeeded, schema matches prior release
  -> Application rollback

Terraform resources wrong, DB unchanged
  -> Infrastructure rollback to prior reviewed plan

Migration failed or schema incompatible with running tasks
  -> Stop promotion, database forward-fix, then application deploy
```

## 6. Abort conditions during rollback

Stop and escalate if:

- ECS services do not reach steady state within the approved change window
- Rollback task definition references an unverified image digest
- RDS failover or storage alarms activate during rollback
- Smoke still fails on the known-good revision

Preserve all evidence before attempting a second rollback strategy.
