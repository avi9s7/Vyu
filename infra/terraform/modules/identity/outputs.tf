output "user_pool_id" {
  description = "Cognito user pool ID."
  value       = aws_cognito_user_pool.vyu.id
}

output "user_pool_arn" {
  description = "Cognito user pool ARN."
  value       = aws_cognito_user_pool.vyu.arn
}

output "web_client_id" {
  description = "Public browser Cognito app client ID. Use as VYU_TOKEN_AUDIENCE."
  value       = aws_cognito_user_pool_client.web.id
}

output "machine_client_id" {
  description = "Confidential machine Cognito app client ID."
  value       = aws_cognito_user_pool_client.machine.id
}

output "machine_client_secret" {
  description = "Confidential machine client secret. Store in Secrets Manager; never commit."
  value       = aws_cognito_user_pool_client.machine.client_secret
  sensitive   = true
}

output "issuer" {
  description = "OIDC issuer URL. Use as VYU_TOKEN_ISSUER."
  value       = local.issuer
}

output "discovery_uri" {
  description = "OIDC discovery URI. Use as VYU_OIDC_DISCOVERY_URI."
  value       = local.discovery_uri
}

output "jwks_uri" {
  description = "JWKS URI. Use as VYU_OIDC_JWKS_URI."
  value       = local.jwks_uri
}

output "hosted_ui_domain" {
  description = "Cognito managed login domain URL."
  value       = "https://${aws_cognito_user_pool_domain.vyu.domain}.auth.${var.aws_region}.amazoncognito.com"
}

output "supported_identity_providers" {
  description = "Cognito identity providers configured for the browser client."
  value       = local.supported_identity_providers
}

output "mfa_configuration" {
  description = "Effective MFA configuration for the user pool."
  value       = local.mfa_configuration
}

output "vyu_operator_env" {
  description = "Environment settings to merge into Vyu deployment operator config."
  value = {
    VYU_AUTH_MODE                     = "oidc_jwks"
    VYU_TOKEN_ISSUER                  = local.issuer
    VYU_TOKEN_AUDIENCE                = aws_cognito_user_pool_client.web.id
    VYU_OIDC_JWKS_URI                 = local.jwks_uri
    VYU_OIDC_DISCOVERY_URI            = local.discovery_uri
    VYU_OIDC_ALLOWED_ALGORITHMS       = "RS256"
    VYU_OIDC_REQUIRED_TOKEN_USE       = var.vyu_required_token_use
    VYU_REQUIRE_EMAIL_VERIFIED        = "true"
    VYU_REQUIRE_TENANT_GOVERNANCE     = "true"
    VYU_IDENTITY_ACCESS_AUDIT_ENABLED = "true"
  }
}
