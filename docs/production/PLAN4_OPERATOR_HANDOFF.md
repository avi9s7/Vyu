# Plan 4 operator handoff

Operator guide for finishing the Plan 4 exit gate after code merge to `main`. Use this document when AWS credentials, DNS, or GitHub reviewer setup require human action.

**Repository:** [avi9s7/Vyu](https://github.com/avi9s7/Vyu)  
**Last updated:** 2026-07-07  
**Verified Git SHA:** `6a9c0662` (see `docs/production/IMPLEMENTATION_STATUS.md`)

---

## 1. What is already implemented

All Plan 4 Tasks 1–10 are merged to `main`:

| Task | Deliverable |
| --- | --- |
| 1 | Terraform module/environment skeleton (`dev` / `staging` / `prod`), remote-state policy |
| 2 | Network + KMS modules |
| 3 | RDS, S3, SQS, Secrets Manager data module |
| 4 | Cognito identity module |
| 5 | ECS compute (web / API / worker / migration), ECR, ALB |
| 6 | CloudFront, WAF, ACM, Route 53 edge module |
| 7 | Observability (alarms, dashboards, ADOT, structured logging) |
| 8 | GitHub OIDC IAM roles, `infra-plan.yml`, `deploy.yml` |
| 9 | Deployment / rollback / secret-rotation runbooks, `deploy_smoke.py` |
| 10 | Backup/restore targets, `verify_restore.py`, database-restore runbook |

**Automation added after merge:**

| Path | Purpose |
| --- | --- |
| `infra/terraform/bootstrap/` | One-time S3 + KMS + DynamoDB remote-state bootstrap |
| `scripts/bootstrap_aws_placeholders.ps1` | Materialize gitignored local `backend.hcl` / `terraform.tfvars` with pilot values |
| `scripts/setup_github_ci_placeholders.ps1` | Create GitHub environments and placeholder CI variables |
| `scripts/sync_backend_hcl_from_bootstrap.ps1` | Copy real bootstrap outputs into environment `backend.hcl` files |
| `scripts/render_github_ci_vars.py` | Print `gh variable set` commands from Terraform outputs |
| `scripts/plan4_operator_checklist.ps1` | Local prerequisite check |
| `scripts/plan4_resume.ps1` | Phase A–E orchestration (`-Phase A`, `-DryRun`) |
| `scripts/install_aws_cli.ps1` | Install AWS CLI v2 on Windows when missing |
| `scripts/seed_plan4_secret_templates.ps1` | Copy secret templates to gitignored `config/` |
| `scripts/setup_github_environment_reviewers.ps1` | Add required reviewers to `staging` / `prod` |
| `infra/terraform/bootstrap/secrets/*.example.*` | Dummy Secrets Manager payloads for post-apply seeding |

**GitHub (live, placeholder values):**

- Environments: `dev`, `staging`, `prod`
- Repository variable: `AWS_PLAN_ROLE_ARN`
- Per-environment variables: `AWS_APPLY_ROLE_ARN`, `AWS_BUILD_ROLE_ARN`, `AWS_PRIVATE_SUBNET_IDS`, `AWS_MIGRATION_SECURITY_GROUP_ID`, `APP_BASE_URL`

**CI status:** `backend`, `frontend`, `platform`, and Infra Plan `policy` jobs pass on `main`. Infra Plan `plan` runs when `AWS_PLAN_ROLE_ARN` is set but fails against AWS until real OIDC roles exist.

### Implementation phase conclusion (2026-07-07)

Plan 4 **code delivery** is complete on `main` (Tasks 1–10, bootstrap stack, CI workflows, runbooks, operator scripts). The **operational exit gate** — staging deploy, rollback, secret rotation, and RDS/S3 restore with bound evidence — remains **operator-blocked** until AWS credentials and DNS are configured (sections 4–5 below).

**Engineering continues with Plan 5** (evidence ingestion) against local PostgreSQL and planned S3 contracts. Plan 4 row in `IMPLEMENTATION_STATUS.md` is `blocked` until operator drills complete; that does not block application-layer Plans 5–8.

---

## 2. Where work stopped

| Step | Status | Blocker |
| --- | --- | --- |
| Remote-state bootstrap (`terraform apply` in `infra/terraform/bootstrap`) | **Not started** | AWS CLI + credentials; globally unique S3 bucket name |
| Dev environment apply | **Not started** | Bootstrap + AWS credentials |
| Replace placeholder GitHub CI variables | **Not started** | Successful dev `terraform apply` outputs |
| Seed Secrets Manager (`configure_secrets.py`) | **Not started** | Dev apply + real secret values |
| Staging deploy / smoke / rollback drill | **Not started** | Staging apply + images + secrets |
| Secret rotation drill | **Not started** | Running staging environment |
| RDS/S3 restore drill with RPO/RTO evidence | **Not started** | Staging data plane + operator window |

**Local machine state (this workspace):**

- `terraform` — installed
- `uv`, `gh` — installed
- `aws` CLI — **not installed**
- Placeholder `backend.hcl` / `terraform.tfvars` — present for all environments
- `infra/terraform/bootstrap/terraform.tfvars` — present (pilot bucket name)

---

## 3. Pilot dummy values in use (replace before production)

| Setting | Pilot value | Replace with |
| --- | --- | --- |
| AWS account ID | `123456789012` | Your real 12-digit account ID |
| State bucket | `vyu-terraform-state-example` | Globally unique S3 bucket name |
| State lock table | `vyu-terraform-state-lock` | Your DynamoDB table name (bootstrap creates it) |
| Route 53 zone ID | `Z000000000000000000000` | Hosted zone ID for your domain |
| Dev hostname | `dev.app.vyu.example` | Real dev FQDN |
| Staging hostname | `staging.app.vyu.example` | Real staging FQDN |
| Prod hostname | `app.vyu.example` | Real prod FQDN |
| Cognito domain prefix | `vyu-dev-login-example` (etc.) | Unique prefix per environment |
| OIDC role ARNs | `arn:aws:iam::123456789012:role/vyu-*` | ARNs from `terraform output` after apply |
| Private subnet IDs | `subnet-0aaa…` | Comma-separated IDs from network module |
| Migration security group | `sg-0placeholdermigration` | `module.network.security_group_ids.migration` |

Full list: `infra/terraform/bootstrap/placeholders.env.example`

---

## 4. Inputs required from you

### 4.1 AWS account and CLI

**Why needed:** Bootstrap and all environment applies run against your AWS account.

**How to obtain:**

1. Sign in to [AWS Console](https://console.aws.amazon.com/).
2. Open **Account** (top-right menu) and note the **12-digit account ID**.
3. Install AWS CLI v2: [Installing AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html), or run:

```powershell
powershell -File scripts/install_aws_cli.ps1
```
4. Configure credentials (pick one):
   - **IAM user (pilot only):** IAM → Users → Security credentials → Create access key. Run `aws configure` and enter access key, secret, region `ap-south-1`.
   - **SSO (preferred):** `aws configure sso` following your org’s IAM Identity Center setup.
5. Verify:

```powershell
aws sts get-caller-identity
```

**Provide to automation:** Account ID and confirmation that `aws sts get-caller-identity` succeeds.

---

### 4.2 Terraform remote state bucket name

**Why needed:** S3 bucket names are globally unique.

**How to obtain:**

1. Choose a name, e.g. `vyu-tfstate-<your-org>-<account-id>`.
2. Edit `infra/terraform/bootstrap/terraform.tfvars`:

```hcl
state_bucket_name = "your-unique-bucket-name"
lock_table_name   = "vyu-terraform-state-lock"
aws_region        = "ap-south-1"
```

3. Bootstrap creates the bucket, KMS key, and lock table.

---

### 4.3 DNS and TLS (Route 53)

**Why needed:** Edge module validates ACM certificates and creates CloudFront / Route 53 records.

**How to obtain:**

1. Register or transfer a domain (e.g. Route 53 or external registrar).
2. Create a **public hosted zone** in Route 53 for your apex domain.
3. Copy the **Hosted zone ID** (format `Z1234567890ABC`).
4. Decide hostnames per environment (examples: `dev.app.example.com`, `staging.app.example.com`, `app.example.com`).
5. Update each environment’s gitignored `terraform.tfvars`:

```hcl
edge_primary_domain_name = "dev.app.example.com"
edge_route53_zone_id     = "Z1234567890ABC"
```

6. If the domain is registered outside Route 53, update the registrar nameservers to the NS records Route 53 provides.

---

### 4.4 Cognito settings

**Why needed:** User login and API authorization in staging/prod drills.

**How to obtain:**

1. Pick a **globally unique** Cognito hosted UI domain prefix per environment (e.g. `vyu-dev-yourorg`).
2. Set callback and logout URLs to match your real HTTPS hostnames in `terraform.tfvars`:

```hcl
identity_callback_urls = ["https://dev.app.example.com/auth/callback"]
identity_logout_urls   = ["https://dev.app.example.com/logout"]
identity_cognito_domain_prefix      = "vyu-dev-yourorg"
identity_resource_server_identifier = "https://api.dev.example.com"
```

3. For enterprise SAML/OIDC, add `identity_saml_identity_providers` or `identity_oidc_identity_providers` per `deploy/aws/cognito/README.md`.

---

### 4.5 GitHub environment reviewers (staging / prod)

**Why needed:** `deploy.yml` uses protected environments; production writes require approval.

**How to obtain:**

1. Open **GitHub → Repository → Settings → Environments**.
2. Select `staging` and `prod`.
3. Enable **Required reviewers** and add your GitHub username (and any security approvers).
4. Optional: add **Wait timer** or **Deployment branches** restrictions per org policy.

**Provide:** GitHub usernames that should be reviewers.

---

### 4.6 Application secrets (Secrets Manager)

**Why needed:** ECS tasks read database and provider credentials from Secrets Manager after apply.

**How to obtain:**

1. After dev `terraform apply`, secrets exist as empty containers:
   - `vyu/dev/database/connection`
   - `vyu/dev/providers`
2. Copy examples and fill real values locally (never commit):

```powershell
copy infra\terraform\bootstrap\secrets\database-connection.example.txt config\dev-database-connection.txt
copy infra\terraform\bootstrap\secrets\providers.example.json config\dev-providers.json
# or:
powershell -File scripts/seed_plan4_secret_templates.ps1 -Environment dev
```

The database secret is a **plain connection URL** (not JSON), stored as the full `VYU_DATABASE_URL` value.

3. Upload with:

```powershell
Get-Content config\dev-database-connection.txt -Raw | uv run python scripts/configure_secrets.py --environment dev --secret-id vyu/dev/database/connection --value-stdin
Get-Content config\dev-providers.json -Raw | uv run python scripts/configure_secrets.py --environment dev --secret-id vyu/dev/providers --value-stdin
```

**Database connection JSON** must match what the API expects (host, port, database, username; password often comes from RDS master secret reference). Inspect `infra/terraform/modules/compute/task_definitions.tf` and application settings for exact keys.

---

### 4.7 Smoke test token (staging deploy drill)

**Why needed:** `deploy_smoke.py` calls authenticated `/v1/me` and research endpoints.

**How to obtain:**

1. Complete Cognito login flow in staging (or create a test user in Cognito console).
2. Obtain a bearer access token from your OAuth/PKCE flow.
3. Export for smoke only (do not commit):

```powershell
$env:VYU_SMOKE_BEARER_TOKEN = "<access-token>"
uv run python scripts/deploy_smoke.py --base-url https://staging.app.example.com
```

See `docs/production/runbooks/deployment.md` for full smoke and evidence capture.

---

## 5. Step-by-step resume sequence

Run from repository root after AWS CLI works.

### Phase A — Bootstrap remote state

```powershell
powershell -File scripts/plan4_operator_checklist.ps1
powershell -File scripts/plan4_resume.ps1 -Phase A
# or step-by-step:
terraform -chdir=infra/terraform/bootstrap init
terraform -chdir=infra/terraform/bootstrap apply
powershell -File scripts/sync_backend_hcl_from_bootstrap.ps1
```

### Phase B — Apply dev

```powershell
terraform -chdir=infra/terraform/environments/dev init -backend-config=backend.hcl
terraform -chdir=infra/terraform/environments/dev plan -out=tfplan
terraform -chdir=infra/terraform/environments/dev apply tfplan
```

### Phase C — Wire GitHub CI with real values

```powershell
uv run python scripts/render_github_ci_vars.py dev
# Run each printed gh variable set command
```

Repeat `render_github_ci_vars.py staging` / `prod` after those environments are applied.

### Phase D — Seed secrets and first deploy

```powershell
# Seed secrets (section 4.6)
# Trigger Deploy workflow: Actions → Deploy → dev → commit SHA from plan artifact
```

### Phase E — Exit gate drills (staging)

Execute in order; capture evidence per runbooks:

1. `docs/production/runbooks/deployment.md` — deploy + smoke
2. `docs/production/runbooks/rollback.md` — ECS revision rollback
3. `docs/production/runbooks/secret-rotation.md` — overlap rotation
4. `docs/production/runbooks/database-restore.md` — PITR + `verify_restore.py`

Update `docs/production/IMPLEMENTATION_STATUS.md` row 4 to `complete` only after all drills pass with bound SHA, digests, and timestamps.

---

## 6. Quick reference commands

| Goal | Command |
| --- | --- |
| Check local prerequisites | `powershell -File scripts/plan4_operator_checklist.ps1` |
| Install AWS CLI (Windows) | `powershell -File scripts/install_aws_cli.ps1` |
| Run handoff phase | `powershell -File scripts/plan4_resume.ps1 -Phase A` |
| Dry-run phase commands | `powershell -File scripts/plan4_resume.ps1 -Phase B -DryRun` |
| Reset pilot tfvars/backend | `powershell -File scripts/bootstrap_aws_placeholders.ps1` |
| Reset placeholder GitHub vars | `powershell -File scripts/setup_github_ci_placeholders.ps1` |
| Infra policy tests | `uv run pytest tests/infra -q` |
| Deploy smoke (after deploy) | `uv run python scripts/deploy_smoke.py --base-url <host>` |
| Restore verification | `uv run python scripts/verify_restore.py --help` |

---

## 7. Related documents

- `docs/superpowers/plans/2026-07-05-vyu-plan-04-aws-deployment.md` — Plan 4 scope and exit gate
- `docs/production/runbooks/deployment.md` — Deploy workflow operator steps
- `infra/terraform/bootstrap/README.md` — Remote-state bootstrap policy
- `docs/production/IMPLEMENTATION_LOG.md` — Commit-level history through Task 10 and bootstrap
