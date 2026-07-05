# VYU AWS Infrastructure and Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provision isolated AWS dev, staging, and production environments and deploy immutable VYU web/API/worker/migration containers through reviewed CI/CD.

**Architecture:** Terraform root modules compose networking, edge security, identity, data, queues, secrets, compute, and observability. ECS Fargate runs separate services behind CloudFront/WAF/ALB. GitHub Actions uses OIDC and environment approvals; no static AWS key is stored in GitHub.

**Tech Stack:** Terraform 1.x, AWS provider, ECS Fargate, ECR, ALB, CloudFront, WAFv2, Cognito, RDS PostgreSQL 17, S3, SQS, KMS, Secrets Manager, CloudWatch, Route 53, ACM, GitHub Actions OIDC.

---

## Entry Gate

- Plans 1-3 are complete.
- API and worker images pass local compose tests.
- AWS organization/account owners have supplied separate account IDs for dev, staging, and production.
- `ap-south-1` is approved for the organization and every required external provider.

## Planned File Map

```text
infra/terraform/
  versions.tf
  modules/
    network/
    kms/
    data/
    queues/
    identity/
    edge/
    compute/
    observability/
    github_oidc/
  environments/
    dev/
    staging/
    prod/
deploy/docker/
  web.Dockerfile
  api.Dockerfile
  worker.Dockerfile
scripts/
  configure_secrets.py
  deploy_smoke.py
  verify_restore.py
docs/production/runbooks/
  deployment.md
  rollback.md
  secret-rotation.md
```

## Task 1: Establish Terraform and Remote-State Policy

**Files:** `infra/terraform/versions.tf`, environment `backend.hcl.example`, `tests/infra/test_terraform_structure.py`

- [ ] Write a failing test asserting required modules/environments exist, provider constraints exist, and no `.tf` file contains plaintext `password`, API-key values, or a local backend.

- [ ] Create `versions.tf` with `required_version = ">= 1.9, < 2.0"`, AWS provider `>= 5.80, < 7.0`, random provider `< 4`, TLS provider `< 5`, and generated `.terraform.lock.hcl` files per environment.

- [ ] Define one encrypted S3 state bucket and DynamoDB-compatible state-lock strategy in the approved infrastructure/bootstrap account. Enable versioning, block public access, KMS encryption, access logging, and deletion protection.

- [ ] Create `backend.hcl.example` with non-secret `bucket`, `key`, `region`, `encrypt`, and KMS key ARN examples. Real account identifiers live in approved CI environment variables, not committed `.tfvars`.

- [ ] Run and commit:

```powershell
terraform -chdir=infra/terraform/environments/dev init -backend=false
terraform -chdir=infra/terraform/environments/dev fmt -check -recursive
terraform -chdir=infra/terraform/environments/dev validate
uv run pytest tests/infra/test_terraform_structure.py -q
git add infra/terraform tests/infra/test_terraform_structure.py
git commit -m "infra: establish Terraform environment structure"
```

## Task 2: Provision Network and Encryption Foundations

**Files:** `modules/network/*`, `modules/kms/*`, environment module calls, `tests/infra/test_network_policy.py`

- [ ] Create a VPC across three availability zones with public ALB subnets, private application subnets, and isolated database subnets. Production uses one NAT gateway per AZ; dev may use one NAT gateway when the cost exception is documented.

- [ ] Create VPC endpoints for S3, ECR API/DKR, CloudWatch Logs, Secrets Manager, SQS, KMS, and STS after verifying regional support.

- [ ] Security groups enforce only:

```text
Internet -> CloudFront/WAF -> ALB : 443
ALB -> web/api ECS groups          : configured container ports
web -> api                         : API port
api/worker/migration -> RDS        : 5432
api/worker -> approved endpoints   : 443 through controlled egress
```

- [ ] Create separate customer-managed KMS keys for data, audit archive, secrets, logs, and state. Enable rotation and least-privilege key policies. No wildcard principal is allowed.

- [ ] Test Terraform plan JSON to prove RDS has no public address, S3 public access is blocked, security groups contain no `0.0.0.0/0` ingress except the CloudFront-restricted ALB path, and KMS rotation is enabled.

- [ ] Commit:

```powershell
git add infra/terraform/modules/network infra/terraform/modules/kms infra/terraform/environments tests/infra/test_network_policy.py
git commit -m "infra: add private network and encryption foundation"
```

## Task 3: Provision RDS, S3, SQS, and Secrets

**Files:** `modules/data/*`, `modules/queues/*`, `scripts/configure_secrets.py`, `tests/infra/test_data_policy.py`

- [ ] RDS production configuration: PostgreSQL 17 supported minor pinned in environment variables, Multi-AZ, private subnets, KMS, deletion protection, 35-day automated backup retention, PITR, controlled maintenance/backup windows, enhanced monitoring, log exports, and parameter-group statement/idle-transaction timeouts.

- [ ] Create `evidence`, `exports`, and `audit` buckets. All have versioning, KMS, public-access block, TLS-only policy, lifecycle rules, access logging, and ownership enforcement. Audit bucket enables Object Lock at creation; staging validates governance mode before production retention is approved.

- [ ] Create four queues and four DLQs: ingestion, research, synthesis, export. Configure long polling, encryption, visibility timeouts per workload, receive count 5, redrive allow policies, and CloudWatch alarms for oldest age, depth, and DLQ messages.

- [ ] Create Secrets Manager containers for database connection metadata and enabled external providers. Terraform creates secret resources and ARNs but never secret versions.

- [ ] Implement `scripts/configure_secrets.py` to accept `--environment`, `--secret-id`, and either `--value-stdin` or `--json-file`; reject command-line plaintext values; call `put_secret_value`; print only ARN/version ID; and return nonzero when AWS identity/environment tags do not match.

- [ ] Tests inspect plan JSON for encryption, retention, public blocks, DLQs, alarms, and absence of secret strings.

- [ ] Commit:

```powershell
git add infra/terraform/modules/data infra/terraform/modules/queues scripts/configure_secrets.py tests/infra/test_data_policy.py
git commit -m "infra: provision encrypted data queues and secret containers"
```

## Task 4: Integrate Cognito and Production Authorization Flow

**Files:** `modules/identity/*`, migrate/reconcile `deploy/aws/cognito/*`, `tests/infra/test_identity_policy.py`

- [ ] Move the useful Cognito resources into the composed identity module instead of keeping a second independent state stack.

- [ ] Configure authorization-code flow only, PKCE-compatible public web client, exact callback/logout URLs, managed login domain, token revocation, deletion protection, MFA `ON` for production, short access/ID tokens, refresh rotation, and enterprise federation inputs.

- [ ] Do not use mutable Cognito custom attributes as authorization truth. Tenant/workspace/role claims are hints; PostgreSQL membership remains authoritative.

- [ ] Configure API resource scopes for research read/write, review write, export write, and admin write. Machine clients use separate confidential clients and narrow scopes.

- [ ] Tests assert implicit flow and password grant are disabled, production MFA is on, callbacks are HTTPS and environment-specific, client secret is false for browser client, and sensitive outputs are marked.

- [ ] Commit:

```powershell
git add infra/terraform/modules/identity deploy/aws/cognito tests/infra/test_identity_policy.py
git commit -m "infra: integrate Cognito authorization code identity"
```

## Task 5: Build Web, API, Worker, and Migration ECS Services

**Files:** `modules/compute/*`, `deploy/docker/web.Dockerfile`, ECS task definitions, `tests/infra/test_compute_policy.py`

- [ ] Create ECR repositories with immutable tags, KMS encryption, scan-on-push, lifecycle retention, and repository policies limited to CI/deployment roles.

- [ ] Build a non-root Next.js 16 standalone web image with production fixture mode rejected at startup.

- [ ] Define separate task roles and execution roles for web, API, worker, and migration. Each role receives only its required queues, buckets, secrets, KMS actions, logs, and database-connect capability.

- [ ] API and web are ECS services behind target groups with health checks. Worker is an ECS service scaled by queue depth. Migration is a one-off task and never a continuously running service.

- [ ] Use deployment circuit breaker with rollback, minimum healthy percentage, graceful stop timeout, read-only root filesystem where compatible, ephemeral storage limits, CPU/memory reservations, and CloudWatch log groups with retention/KMS.

- [ ] Task definitions reference image digests and secret ARNs. They do not contain plaintext credentials, mutable `latest`, or local file paths.

- [ ] Terraform plan tests assert non-root/read-only settings, distinct roles, no public task IP, secret references, log encryption, image digest format, and worker autoscaling.

- [ ] Commit:

```powershell
git add infra/terraform/modules/compute deploy/docker/web.Dockerfile tests/infra/test_compute_policy.py
git commit -m "infra: add isolated ECS application services"
```

## Task 6: Add CloudFront, WAF, TLS, DNS, and Safe Request Limits

**Files:** `modules/edge/*`, `tests/infra/test_edge_policy.py`

- [ ] ACM certificate validation uses Route 53. HTTP redirects to HTTPS. HSTS, CSP, frame, MIME, referrer, and permissions headers are set at CloudFront/web.

- [ ] WAF enables AWS managed common, known-bad-input, IP reputation, and SQL-injection rule groups plus rate limits. Upload and API paths have explicit body-size policies; larger direct uploads use S3 presigned URLs instead of ALB bodies.

- [ ] CloudFront uses origin access controls where S3 is an origin, does not cache authenticated API responses, forwards only required headers/cookies/query fields, and logs requests without authorization/cookie values.

- [ ] ALB accepts traffic from the approved CloudFront origin path or documented machine-client API path. Direct unprotected origin access is blocked.

- [ ] Tests prove TLS policy, HTTPS redirect, WAF association, no API caching, safe headers, and public S3 denial.

- [ ] Commit:

```powershell
git add infra/terraform/modules/edge tests/infra/test_edge_policy.py
git commit -m "infra: protect VYU edge with TLS CloudFront and WAF"
```

## Task 7: Add Metrics, Logs, Traces, Dashboards, and Alarms

**Files:** `modules/observability/*`, `src/vyu/observability/*`, `tests/infra/test_observability_policy.py`

- [ ] Deploy an OpenTelemetry Collector sidecar or approved managed collector configuration for API/worker traces and metrics. Logs remain structured JSON to stdout.

- [ ] Create dashboards and alarms for ALB 5xx/latency, ECS health/CPU/memory, RDS connections/storage/latency/failover, queue depth/age/DLQ, Cognito auth failures, WAF blocks, job failures, connector failures, model latency/cost, audit failures, and backup status.

- [ ] Alarm actions route to environment-specific SNS/on-call destinations. Production critical alarms require acknowledged ownership before apply.

- [ ] Log groups have environment-specific retention and KMS. Application logs never include request bodies, tokens, cookies, prompts, document text, or secret values.

- [ ] Terraform tests assert every production service has logs, dashboard coverage, critical alarms, and action targets.

- [ ] Commit:

```powershell
git add infra/terraform/modules/observability src/vyu/observability tests/infra/test_observability_policy.py
git commit -m "infra: add production telemetry and alarms"
```

## Task 8: Configure GitHub OIDC and Deployment Roles

**Files:** `modules/github_oidc/*`, `.github/workflows/infra-plan.yml`, `.github/workflows/deploy.yml`, `tests/infra/test_ci_identity_policy.py`

- [ ] Trust policies restrict repository, branch/environment, audience, and workflow. Pull requests receive plan-only roles. Staging/prod apply roles require protected GitHub environments; production requires owner approval.

- [ ] Workflows use immutable action SHAs, minimal `permissions`, `id-token: write` only in deploy jobs, artifact attestations, concurrency locks, and no long-lived AWS keys.

- [ ] PR workflow runs fmt, validate, lint, security/policy scans, and uploads a reviewed plan artifact with expiration. Apply workflow downloads the exact plan artifact and verifies commit SHA before apply.

- [ ] Container workflow builds once, generates SBOMs, scans, signs, pushes immutable images, and passes digests to Terraform/deployment. Dev, staging, and prod reuse the same image digests.

- [ ] Database migration task runs before service promotion; a failed migration blocks deployment. Post-deploy smoke failure triggers ECS rollback and records evidence.

- [ ] Tests inspect workflow YAML and trust-policy JSON for broad subjects, write permissions, mutable actions, static AWS secrets, or apply on pull requests.

- [ ] Commit:

```powershell
git add infra/terraform/modules/github_oidc .github/workflows tests/infra/test_ci_identity_policy.py
git commit -m "ci: deploy AWS through least-privilege OIDC"
```

## Task 9: Write Deployment, Rollback, and Secret-Rotation Runbooks

**Files:** `docs/production/runbooks/deployment.md`, `rollback.md`, `secret-rotation.md`, `scripts/deploy_smoke.py`

- [ ] Deployment runbook contains prerequisites, identity verification, secret presence checks, plan review, migration, service deploy, smoke commands, dashboard checks, evidence capture, and abort conditions.

- [ ] Rollback runbook distinguishes application rollback, infrastructure rollback, and database forward-fix. Include exact ECS service revision rollback, image digest verification, smoke checks, incident/audit record, and data-migration escalation.

- [ ] Secret rotation runbook covers provider key overlap, `put-secret-value`, forced ECS new deployment, health verification, old credential revocation, and audit record. It explicitly notes that ECS environment-injected secrets do not refresh in running tasks.

- [ ] `deploy_smoke.py` verifies HTTPS, liveness/readiness/version, unauthenticated rejection, authenticated `/v1/me`, idempotent research submission, queue/job visibility, and safe headers without printing tokens.

- [ ] Run a staging deploy, rollback, and secret-rotation exercise. Attach timestamps, deployment IDs, image digests, migration revision, smoke output, alarm state, and operator names to release evidence.

- [ ] Commit:

```powershell
git add docs/production/runbooks scripts/deploy_smoke.py
git commit -m "docs: add AWS deployment and recovery runbooks"
```

## Task 10: Prove Backup and Restore

**Files:** `scripts/verify_restore.py`, `docs/production/runbooks/database-restore.md`, status evidence

- [ ] Enable RDS automated backups/PITR and S3 version/lifecycle recovery. Define pilot RPO <= 15 minutes and RTO <= 4 hours.

- [ ] In staging, write a known tenant/workspace/research/audit fixture, record hashes, restore RDS to a new instance at a chosen point, and point an isolated verification task at the restored database.

- [ ] `verify_restore.py` checks migration revision, fixture hashes, tenant isolation, audit presence, and absence of post-restore-point records.

- [ ] Restore selected S3 object versions and verify database checksum/version references.

- [ ] Record measured RPO/RTO, gaps, cleanup, and owner approval. Do not call a snapshot-created event a restore test.

- [ ] Update Plan 4 status only after dev and staging plans/applies, service smoke, rollback, rotation, and restore pass.

## Exit Gate

- Separate AWS accounts/environments exist with isolated state and data.
- Terraform plan tests prove private networking, encryption, least privilege, backups, WAF, logs, alarms, and no plaintext secrets.
- Web/API/worker/migration run as distinct non-root ECS tasks from immutable signed digests.
- GitHub deploys via OIDC and protected environments; no static AWS keys exist.
- Cognito PKCE login and database-backed authorization work in staging.
- Staging deployment, migration, smoke, rollback, secret rotation, and RDS/S3 restore exercises pass.
- RPO/RTO evidence meets the pilot target.
- Plan 4 evidence is bound to Git SHA, image digests, Terraform plan/apply IDs, migration revision, and AWS account/environment.

## Handoff

Plans 5-9 deploy through this platform. They add only module inputs, task permissions, secrets, queues, alarms, and routes required by their bounded capability; they do not create parallel infrastructure stacks.

