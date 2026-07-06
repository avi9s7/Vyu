resource "aws_cognito_user_pool" "vyu" {
  name                = "${local.name_prefix}-user-pool"
  deletion_protection = local.deletion_protection

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  mfa_configuration        = local.mfa_configuration

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
  domain       = var.cognito_domain_prefix
  user_pool_id = aws_cognito_user_pool.vyu.id
}

resource "aws_cognito_resource_server" "vyu_api" {
  identifier   = var.resource_server_identifier
  name         = "${local.name_prefix}-api"
  user_pool_id = aws_cognito_user_pool.vyu.id

  dynamic "scope" {
    for_each = local.api_scopes

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
  description  = "Vyu role group mapped into application RBAC hints."
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

resource "aws_cognito_user_pool_client" "web" {
  name         = "${local.name_prefix}-web-client"
  user_pool_id = aws_cognito_user_pool.vyu.id

  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = local.web_allowed_oauth_scopes
  callback_urls                        = var.callback_urls
  logout_urls                          = var.logout_urls
  supported_identity_providers         = local.supported_identity_providers

  explicit_auth_flows = [
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH",
  ]

  read_attributes  = local.read_attributes
  write_attributes = local.write_attributes

  access_token_validity  = local.access_token_validity
  id_token_validity      = local.id_token_validity
  refresh_token_validity = var.refresh_token_validity_days

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  refresh_token_rotation {
    feature                    = "ENABLED"
    retry_grace_period_seconds = var.refresh_token_rotation_grace_period_seconds
  }

  enable_token_revocation       = true
  prevent_user_existence_errors = "ENABLED"

  depends_on = [
    aws_cognito_identity_provider.saml,
    aws_cognito_identity_provider.oidc,
    aws_cognito_resource_server.vyu_api,
  ]
}
