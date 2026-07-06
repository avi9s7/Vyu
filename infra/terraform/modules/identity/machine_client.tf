resource "aws_cognito_user_pool_client" "machine" {
  name         = "${local.name_prefix}-machine-client"
  user_pool_id = aws_cognito_user_pool.vyu.id

  generate_secret                      = true
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["client_credentials"]
  allowed_oauth_scopes                 = local.machine_allowed_oauth_scopes

  explicit_auth_flows = [
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

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
    aws_cognito_resource_server.vyu_api,
  ]
}
