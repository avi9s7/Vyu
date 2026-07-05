locals {
  user_pool_name = var.user_pool_name != "" ? var.user_pool_name : "${var.name_prefix}-user-pool"
  app_client_name = var.app_client_name != "" ? var.app_client_name : "${var.name_prefix}-app-client"

  domain_enabled = trimspace(var.cognito_domain_prefix) != ""

  custom_attributes = {
    vyu_tenant_id = 128
    vyu_workspace_id = 128
    vyu_roles = 2048
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
    email                   = "email"
    email_verified          = "email_verified"
    "custom:vyu_tenant_id"    = "vyu_tenant_id"
    "custom:vyu_workspace_id" = "vyu_workspace_id"
    "custom:vyu_roles"        = "vyu_roles"
  }

  resource_server_scope_identifiers = [
    for scope in var.resource_server_scopes : "${var.resource_server_identifier}/${scope.name}"
  ]

  allowed_oauth_scopes = distinct(concat(
    ["openid", "email", "profile"],
    local.resource_server_scope_identifiers,
  ))

  supported_identity_providers = distinct(concat(
    ["COGNITO"],
    keys(var.saml_identity_providers),
    keys(var.oidc_identity_providers),
  ))

  issuer        = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.vyu.id}"
  discovery_uri = "${local.issuer}/.well-known/openid-configuration"
  jwks_uri      = "${local.issuer}/.well-known/jwks.json"
}

resource "aws_cognito_user_pool" "vyu" {
  name                = local.user_pool_name
  deletion_protection = var.deletion_protection ? "ACTIVE" : "INACTIVE"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  mfa_configuration        = var.mfa_configuration

  admin_create_user_config {
    allow_admin_create_user_only = var.admin_create_user_only
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  password_policy {
    minimum_length                   = 14
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = var.temporary_password_validity_days
  }

  user_attribute_update_settings {
    attributes_require_verification_before_update = ["email"]
  }

  schema {
    name                = "email"
    attribute_data_type = "String"
    mutable             = true
    required            = true

    string_attribute_constraints {
      min_length = "5"
      max_length = "320"
    }
  }

  dynamic "schema" {
    for_each = local.custom_attributes

    content {
      name                = schema.key
      attribute_data_type = "String"
      mutable             = true
      required            = false

      string_attribute_constraints {
        min_length = "1"
        max_length = tostring(schema.value)
      }
    }
  }
}

resource "aws_cognito_user_pool_domain" "vyu" {
  count        = local.domain_enabled ? 1 : 0
  domain       = var.cognito_domain_prefix
  user_pool_id = aws_cognito_user_pool.vyu.id
}

resource "aws_cognito_resource_server" "vyu_api" {
  identifier   = var.resource_server_identifier
  name         = "${var.name_prefix}-api"
  user_pool_id = aws_cognito_user_pool.vyu.id

  dynamic "scope" {
    for_each = var.resource_server_scopes

    content {
      scope_name        = scope.value.name
      scope_description = scope.value.description
    }
  }
}

resource "aws_cognito_user_group" "vyu_roles" {
  for_each = var.role_groups

  user_pool_id = aws_cognito_user_pool.vyu.id
  name         = each.key
  description  = "Vyu role group mapped into application RBAC and tenant governance."
  precedence   = each.value
}

resource "aws_cognito_identity_provider" "saml" {
  for_each = var.saml_identity_providers

  user_pool_id  = aws_cognito_user_pool.vyu.id
  provider_name = each.key
  provider_type = "SAML"

  provider_details = merge(
    each.value.metadata_url != null ? { MetadataURL = each.value.metadata_url } : {},
    each.value.metadata_file != null ? { MetadataFile = file(each.value.metadata_file) } : {},
    each.value.provider_details,
  )

  attribute_mapping = merge(
    local.default_idp_attribute_mapping,
    each.value.attribute_mapping,
  )
}

resource "aws_cognito_identity_provider" "oidc" {
  for_each = var.oidc_identity_providers

  user_pool_id  = aws_cognito_user_pool.vyu.id
  provider_name = each.key
  provider_type = "OIDC"

  provider_details = merge(
    {
      attributes_request_method = each.value.attributes_request_method
      authorize_scopes          = join(" ", each.value.authorize_scopes)
      authorize_url             = each.value.authorize_url
      jwks_uri                  = each.value.jwks_uri
      oidc_issuer               = each.value.issuer_url
      token_url                 = each.value.token_url
    },
    each.value.user_info_url != null ? { attributes_url = each.value.user_info_url } : {},
    each.value.provider_details,
  )

  attribute_mapping = merge(
    local.default_idp_attribute_mapping,
    each.value.attribute_mapping,
  )
}

resource "aws_cognito_user_pool_client" "vyu_app" {
  name         = local.app_client_name
  user_pool_id = aws_cognito_user_pool.vyu.id

  generate_secret                      = var.generate_client_secret
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = local.allowed_oauth_scopes
  callback_urls                        = var.callback_urls
  logout_urls                          = var.logout_urls
  supported_identity_providers         = local.supported_identity_providers

  explicit_auth_flows = [
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH",
  ]

  read_attributes  = local.read_attributes
  write_attributes = local.write_attributes

  access_token_validity  = var.access_token_validity_minutes
  id_token_validity      = var.id_token_validity_minutes
  refresh_token_validity = var.refresh_token_validity_days

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  enable_token_revocation       = true
  prevent_user_existence_errors = "ENABLED"

  depends_on = [
    aws_cognito_identity_provider.saml,
    aws_cognito_identity_provider.oidc,
    aws_cognito_resource_server.vyu_api,
  ]
}
