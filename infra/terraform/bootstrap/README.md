# Remote Terraform state bootstrap policy

VYU uses one encrypted S3 state bucket and a DynamoDB-compatible lock table per
organization bootstrap account. Real bucket names, KMS key ARNs, and account IDs
are supplied through approved CI environment variables and `backend.hcl` files
that are never committed with production identifiers.

## Required controls

- Versioning enabled on the state bucket
- Block all public access
- SSE-KMS encryption with a customer-managed key
- Access logging to a dedicated logging bucket
- Deletion protection / object lock where the account policy allows
- DynamoDB table (or equivalent) for state locking

## Usage

Copy `environments/<env>/backend.hcl.example` to a local, untracked `backend.hcl`
and substitute approved values before `terraform init`.

### One-time remote state bootstrap

Apply the bootstrap stack with admin credentials before any environment root:

```powershell
copy infra\terraform\bootstrap\terraform.tfvars.example infra\terraform\bootstrap\terraform.tfvars
terraform -chdir=infra/terraform/bootstrap init
terraform -chdir=infra/terraform/bootstrap apply
powershell -File scripts/sync_backend_hcl_from_bootstrap.ps1
```

Pilot placeholders (replace before any real apply):

```powershell
powershell -File scripts/bootstrap_aws_placeholders.ps1
powershell -File scripts/setup_github_ci_placeholders.ps1
```

After a successful environment `terraform apply`, regenerate real GitHub variable commands with:

```powershell
uv run python scripts/render_github_ci_vars.py dev
```

Operator prerequisite check:

```powershell
powershell -File scripts/plan4_operator_checklist.ps1
```

See `placeholders.env.example` for the documented dummy account, state bucket, and hostname values.
