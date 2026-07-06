locals {
  environment = var.environment != "" ? var.environment : (
    startswith(var.name_prefix, "vyu-") ? replace(var.name_prefix, "vyu-", "") : "prod"
  )
}

module "identity" {
  source = "../../../infra/terraform/modules/identity"

  environment                = local.environment
  aws_region                 = var.aws_region
  callback_urls              = var.callback_urls
  logout_urls                = var.logout_urls
  cognito_domain_prefix      = var.cognito_domain_prefix
  resource_server_identifier = var.resource_server_identifier
  saml_identity_providers    = var.saml_identity_providers
  oidc_identity_providers    = var.oidc_identity_providers
  admin_create_user_only     = var.admin_create_user_only
  deletion_protection        = var.deletion_protection
  non_production_mfa_configuration = var.mfa_configuration
  access_token_validity_minutes    = var.access_token_validity_minutes
  id_token_validity_minutes        = var.id_token_validity_minutes
  refresh_token_validity_days        = var.refresh_token_validity_days
  vyu_required_token_use             = var.vyu_required_token_use
  role_groups                        = var.role_groups
}
