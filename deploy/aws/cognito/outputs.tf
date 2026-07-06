output "user_pool_id" {
  description = "Cognito user pool ID."
  value       = module.identity.user_pool_id
}

output "user_pool_arn" {
  description = "Cognito user pool ARN."
  value       = module.identity.user_pool_arn
}

output "app_client_id" {
  description = "Deprecated alias for web_client_id."
  value       = module.identity.web_client_id
}

output "web_client_id" {
  description = "Public browser Cognito app client ID."
  value       = module.identity.web_client_id
}

output "machine_client_id" {
  description = "Confidential machine Cognito app client ID."
  value       = module.identity.machine_client_id
}

output "app_client_secret" {
  description = "Deprecated. Browser clients do not have secrets. Use machine_client_secret for M2M clients."
  value       = null
  sensitive   = true
}

output "machine_client_secret" {
  description = "Confidential machine client secret."
  value       = module.identity.machine_client_secret
  sensitive   = true
}

output "issuer" {
  description = "OIDC issuer URL."
  value       = module.identity.issuer
}

output "discovery_uri" {
  description = "OIDC discovery URI."
  value       = module.identity.discovery_uri
}

output "jwks_uri" {
  description = "JWKS URI."
  value       = module.identity.jwks_uri
}

output "hosted_ui_domain" {
  description = "Cognito managed login domain URL."
  value       = module.identity.hosted_ui_domain
}

output "supported_identity_providers" {
  description = "Configured identity providers."
  value       = module.identity.supported_identity_providers
}

output "vyu_operator_env" {
  description = "Operator environment overlay for Vyu deployments."
  value       = module.identity.vyu_operator_env
}
