# Vyu AWS Cognito Provisioning

This Terraform stack provisions the Cognito identity-provider boundary for AWS-hosted Vyu deployments.

It creates:

- Cognito user pool with email sign-in, email verification, production password policy, optional MFA, and deletion protection.
- Cognito app client configured for OAuth authorization-code flow.
- Optional Cognito Hosted UI domain.
- Vyu API resource server and OAuth scopes.
- Cognito groups that map to Vyu roles: `researcher`, `reviewer`, `workspace_admin`, and `tenant_admin`.
- Custom attributes that Vyu can read from ID tokens: `custom:vyu_tenant_id`, `custom:vyu_workspace_id`, and `custom:vyu_roles`.
- Optional enterprise SAML or OIDC identity providers federated through Cognito.
- Terraform outputs that can be merged directly into Vyu operator environment configuration.

## Apply

```bash
cd deploy/aws/cognito
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan -out tfplan
terraform apply tfplan
terraform output -json > cognito-outputs.json
```

## Render Vyu operator env overlay

```bash
python ../../../scripts/render_cognito_operator_env.py \
  --terraform-output-json cognito-outputs.json \
  --tenant-governance-registry /app/config/tenant-governance.json \
  --output deployment.cognito.env
```

Merge the generated overlay with the rest of the deployment config, including `VYU_SQLITE_DB`, `VYU_PHASE_OUTPUT_DIR`, `VYU_TENANT_ID`, `VYU_WORKSPACE_ID`, and any API-key or serverless settings.

## Token and claim model

Vyu validates Cognito/OIDC JWTs with `VYU_AUTH_MODE=oidc_jwks`. This stack emits both JWKS and discovery URIs. By default Vyu requires Cognito ID tokens (`token_use=id`) because ID tokens carry user attributes and `cognito:groups`.

Vyu accepts both its provider-neutral claim names and Cognito-native names:

| Vyu meaning | Provider-neutral claim | Cognito-native claim |
|---|---|---|
| Tenant | `vyu.tenant_id` | `custom:vyu_tenant_id` |
| Workspace | `vyu.workspace_id` | `custom:vyu_workspace_id` |
| Roles | `vyu.roles`, `groups` | `cognito:groups`, `custom:vyu_roles` |

Cognito groups and token attributes are still treated as requested access. Vyu tenant governance remains the final authority and should be required in production with `VYU_REQUIRE_TENANT_GOVERNANCE=true`.

## Enterprise SAML/OIDC federation

Use `saml_identity_providers` or `oidc_identity_providers` to broker enterprise IdPs through Cognito. Map upstream attributes into the Cognito attributes above. Vyu should not process raw SAML XML inside the application runtime; Cognito validates upstream IdP assertions and emits the signed OIDC token that Vyu verifies.

## Production notes

- Use a remote Terraform backend with state encryption and locking before applying this stack in a real account.
- Protect the app client secret if `generate_client_secret=true`. Vyu JWT validation does not need the client secret.
- Keep tenant grants, service-account keys, and API-key records in the tenant-governance registry or its production-backed replacement.
- Review callback/logout URLs, hosted UI domain names, and IdP metadata during release review.
