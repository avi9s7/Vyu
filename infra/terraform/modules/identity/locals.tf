locals {
  is_production = var.environment == "prod"
  name_prefix   = "vyu-${var.environment}"

  # Custom Cognito attributes are authentication hints only.
  # PostgreSQL membership and tenant governance remain authoritative.
  custom_attributes = {
    vyu_tenant_id    = 128
    vyu_workspace_id = 128
    vyu_roles        = 2048
  }

  standard_read_attributes = [
    "email",
    "email_verified",
  ]

  custom_read_attributes = [
    "custom:vyu_tenant_id",
    "custom:vyu_workspace_id",
    "custom:vyu_roles",
  ]

  read_attributes  = concat(local.standard_read_attributes, local.custom_read_attributes)
  write_attributes = local.read_attributes

  default_idp_attribute_mapping = {
    email                     = "email"
    email_verified            = "email_verified"
    "custom:vyu_tenant_id"    = "vyu_tenant_id"
    "custom:vyu_workspace_id" = "vyu_workspace_id"
    "custom:vyu_roles"        = "vyu_roles"
  }

  api_scopes = [
    {
      name        = "research.read"
      description = "Read governed research and evidence resources."
    },
    {
      name        = "research.write"
      description = "Create and update governed research runs."
    },
    {
      name        = "review.write"
      description = "Submit governed review decisions."
    },
    {
      name        = "export.write"
      description = "Request and download governed exports."
    },
    {
      name        = "admin.write"
      description = "Perform governed tenant administration."
    },
  ]

  resource_server_scope_identifiers = [
    for scope in local.api_scopes : "${var.resource_server_identifier}/${scope.name}"
  ]

  web_allowed_oauth_scopes = distinct(concat(
    ["openid", "email", "profile"],
    local.resource_server_scope_identifiers,
  ))

  machine_allowed_oauth_scopes = [
    "${var.resource_server_identifier}/research.read",
    "${var.resource_server_identifier}/export.write",
  ]

  supported_identity_providers = distinct(concat(
    ["COGNITO"],
    keys(var.saml_identity_providers),
    keys(var.oidc_identity_providers),
  ))

  mfa_configuration     = local.is_production ? "ON" : var.non_production_mfa_configuration
  deletion_protection   = local.is_production ? "ACTIVE" : var.deletion_protection ? "ACTIVE" : "INACTIVE"
  access_token_validity = local.is_production ? 15 : var.access_token_validity_minutes
  id_token_validity     = local.is_production ? 15 : var.id_token_validity_minutes

  issuer        = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.vyu.id}"
  discovery_uri = "${local.issuer}/.well-known/openid-configuration"
  jwks_uri      = "${local.issuer}/.well-known/jwks.json"
}
