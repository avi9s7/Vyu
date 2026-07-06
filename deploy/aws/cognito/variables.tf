variable "aws_region" {
  description = "AWS region where the Cognito user pool is provisioned."
  type        = string
}

variable "environment" {
  description = "Deployment environment name (dev, staging, prod)."
  type        = string
  default     = ""
}

variable "name_prefix" {
  description = "Deprecated compatibility prefix. Use environment when possible."
  type        = string
  default     = ""
}

variable "callback_urls" {
  description = "Allowed Hosted UI/OIDC callback URLs for the browser client."
  type        = list(string)
}

variable "logout_urls" {
  description = "Allowed Hosted UI/OIDC logout URLs for the browser client."
  type        = list(string)
}

variable "cognito_domain_prefix" {
  description = "Globally unique Cognito managed login domain prefix."
  type        = string
}

variable "resource_server_identifier" {
  description = "OAuth resource-server identifier for Vyu API scopes."
  type        = string
  default     = "https://api.vyu.local"
}

variable "deletion_protection" {
  type    = bool
  default = true
}

variable "admin_create_user_only" {
  type    = bool
  default = true
}

variable "mfa_configuration" {
  description = "Non-production MFA mode. Production environments always use ON in the composed module."
  type        = string
  default     = "OPTIONAL"

  validation {
    condition     = contains(["OFF", "ON", "OPTIONAL"], var.mfa_configuration)
    error_message = "mfa_configuration must be OFF, ON, or OPTIONAL."
  }
}

variable "temporary_password_validity_days" {
  type    = number
  default = 7
}

variable "access_token_validity_minutes" {
  type    = number
  default = 60
}

variable "id_token_validity_minutes" {
  type    = number
  default = 60
}

variable "refresh_token_validity_days" {
  type    = number
  default = 1
}

variable "vyu_required_token_use" {
  type    = string
  default = "id"

  validation {
    condition     = contains(["id", "access"], var.vyu_required_token_use)
    error_message = "vyu_required_token_use must be id or access."
  }
}

variable "role_groups" {
  type = map(number)
  default = {
    researcher      = 40
    reviewer        = 30
    workspace_admin = 20
    tenant_admin    = 10
  }
}

variable "saml_identity_providers" {
  type = map(object({
    metadata_url      = optional(string)
    metadata_file     = optional(string)
    provider_details  = optional(map(string), {})
    attribute_mapping = optional(map(string), {})
  }))
  default = {}
}

variable "oidc_identity_providers" {
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

variable "tags" {
  type    = map(string)
  default = {}
}
