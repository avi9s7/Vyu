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
