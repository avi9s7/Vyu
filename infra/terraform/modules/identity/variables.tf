variable "environment" {
  type = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging, or prod."
  }
}

variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "callback_urls" {
  description = "Allowed Hosted UI/OIDC callback URLs for the browser client."
  type        = list(string)

  validation {
    condition = length(var.callback_urls) > 0 && alltrue([
      for url in var.callback_urls : startswith(url, "https://")
    ])
    error_message = "callback_urls must be non-empty HTTPS URLs."
  }
}

variable "logout_urls" {
  description = "Allowed Hosted UI/OIDC logout URLs for the browser client."
  type        = list(string)

  validation {
    condition = length(var.logout_urls) > 0 && alltrue([
      for url in var.logout_urls : startswith(url, "https://")
    ])
    error_message = "logout_urls must be non-empty HTTPS URLs."
  }
}

variable "cognito_domain_prefix" {
  description = "Globally unique Cognito managed login domain prefix."
  type        = string

  validation {
    condition     = length(trimspace(var.cognito_domain_prefix)) > 0
    error_message = "cognito_domain_prefix is required for managed login."
  }
}

variable "resource_server_identifier" {
  description = "OAuth resource-server identifier for Vyu API scopes."
  type        = string
}

variable "deletion_protection" {
  description = "Enable Cognito user-pool deletion protection outside production defaults."
  type        = bool
  default     = true
}

variable "admin_create_user_only" {
  description = "When true, only administrators can create users directly in the user pool."
  type        = bool
  default     = true
}

variable "non_production_mfa_configuration" {
  description = "MFA mode for dev and staging. Production always uses ON."
  type        = string
  default     = "OPTIONAL"

  validation {
    condition     = contains(["OFF", "ON", "OPTIONAL"], var.non_production_mfa_configuration)
    error_message = "non_production_mfa_configuration must be OFF, ON, or OPTIONAL."
  }
}

variable "temporary_password_validity_days" {
  type    = number
  default = 7
}

variable "access_token_validity_minutes" {
  description = "Access-token validity in minutes for non-production environments."
  type        = number
  default     = 60
}

variable "id_token_validity_minutes" {
  description = "ID-token validity in minutes for non-production environments."
  type        = number
  default     = 60
}

variable "refresh_token_validity_days" {
  type    = number
  default = 1
}

variable "refresh_token_rotation_grace_period_seconds" {
  type    = number
  default = 10

  validation {
    condition     = var.refresh_token_rotation_grace_period_seconds >= 0 && var.refresh_token_rotation_grace_period_seconds <= 60
    error_message = "refresh_token_rotation_grace_period_seconds must be between 0 and 60."
  }
}

variable "vyu_required_token_use" {
  description = "Token-use claim Vyu requires when validating Cognito JWTs."
  type        = string
  default     = "id"

  validation {
    condition     = contains(["id", "access"], var.vyu_required_token_use)
    error_message = "vyu_required_token_use must be id or access."
  }
}

variable "role_groups" {
  description = "Cognito groups mapped into application RBAC hints."
  type        = map(number)
  default = {
    researcher      = 40
    reviewer        = 30
    workspace_admin = 20
    tenant_admin    = 10
  }
}

variable "saml_identity_providers" {
  description = "Optional enterprise SAML IdPs federated through Cognito."
  type = map(object({
    metadata_url      = optional(string)
    metadata_file     = optional(string)
    provider_details  = optional(map(string), {})
    attribute_mapping = optional(map(string), {})
  }))
  default = {}
}

variable "oidc_identity_providers" {
  description = "Optional enterprise OIDC IdPs federated through Cognito."
  type = map(object({
    issuer_url                = string
    authorize_url             = string
    token_url                 = string
    jwks_uri                  = string
    user_info_url             = optional(string)
    authorize_scopes          = optional(list(string), ["openid", "email", "profile"])
    attributes_request_method = optional(string, "GET")
    provider_details          = optional(map(string), {})
    attribute_mapping         = optional(map(string), {})
  }))
  default = {}
}
