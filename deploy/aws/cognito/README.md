# Vyu AWS Cognito Provisioning

This directory is a compatibility wrapper around the composed Terraform identity module at `infra/terraform/modules/identity`.

New deployments should apply Cognito through the environment roots in `infra/terraform/environments/{dev,staging,prod}` instead of maintaining a second independent state stack here.

## Apply (compatibility wrapper)

```bash
cd deploy/aws/cognito
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan -out tfplan
terraform apply tfplan
terraform output -json > cognito-outputs.json
```

Set `environment = "prod"` (or `dev` / `staging`) in `terraform.tfvars` so production MFA and token policies match the composed module.

## Render Vyu operator env overlay

```bash
python ../../../scripts/render_cognito_operator_env.py \
  --terraform-output-json cognito-outputs.json \
  --tenant-governance-registry /app/config/tenant-governance.json \
  --output deployment.cognito.env
```

## Token and claim model

Vyu validates Cognito/OIDC JWTs with `VYU_AUTH_MODE=oidc_jwks`. Cognito custom attributes and groups are authentication hints only; PostgreSQL membership and tenant governance remain authoritative.

| Vyu meaning | Provider-neutral claim | Cognito-native claim |
|---|---|---|
| Tenant | `vyu.tenant_id` | `custom:vyu_tenant_id` |
| Workspace | `vyu.workspace_id` | `custom:vyu_workspace_id` |
| Roles | `vyu.roles`, `groups` | `cognito:groups`, `custom:vyu_roles` |

## Enterprise SAML/OIDC federation

Configure `saml_identity_providers` or `oidc_identity_providers` in the environment root or this wrapper's `terraform.tfvars`. Cognito brokers upstream IdPs and emits signed OIDC tokens for Vyu to verify.
