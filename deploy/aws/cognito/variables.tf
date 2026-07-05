variable "aws_region" {
  description = "AWS region where the Cognito user pool is provisioned."
  type        = string
}

variable "name_prefix" {
  description = "Name prefix for Vyu Cognito resources."
  type        = string
  default     = "vyu-prod"
}

variable "user_pool_name" {
  description = "Optional explicit Cognito user pool name. Defaults to <name_prefix>-user-pool."
  type        = string
  default     = ""
}

variable "app_client_name" {
  description = "Optional explicit Cognito app client name. Defaults to <name_prefix>-app-client."
  type        = string
  default     = ""
}

variable "resource_server_identifier" {
  description = "OAuth resource-server identifier for Vyu API scopes."
  type        = string
  default     = "https://api.vyu.local"
}

variable "resource_server_scopes" {
  description = "Vyu API scopes to expose through the Cognito app client."
  type = list(object({
    name        = string
    description = string
  }))
  default = [
    {
      name        = "research.read"
      description = "Read governed research and evidence resources."
    },
    {
      name        = "review.write"
      description = "Submit governed review decisions."
    },
    {
      name        = "admin.write"
      description = "Perform governed tenant administration."
    },
  ]
}

variable "callback_urls" {
  description = "Allowed Hosted UI/OIDC callback URLs for the Vyu frontend or API client."
  type        = list(string)
}

variable "logout_urls" {
  description = "Allowed Hosted UI/OIDC logout URLs for the Vyu frontend or API client."
  type        = list(string)
}

variable "cognito_domain_prefix" {
  description = "Optional Cognito hosted UI domain prefix. Leave empty to skip domain creation."
  type        = string
  default     = ""
}

variable "generate_client_secret" {
  description = "Whether the app client should have a client secret. Browser/SPAs usually set this false; confidential server clients may set true."
  type        = bool
  default     = false
}

variable "deletion_protection" {
  description = "Enable Cognito user-pool deletion protection. Recommended for production."
  type        = bool
  default     = true
}

variable "admin_create_user_only" {
  description = "When true, only administrators can create users directly in the user pool. Federated IdPs can still sign in through their configured providers."
  type        = bool
  default     = true
}

variable "mfa_configuration" {
  description = "Cognito MFA mode. Use ON or OPTIONAL for production unless enterprise MFA is enforced by the upstream IdP."
  type        = string
  default     = "OPTIONAL"

  validation {
    condition     = contains(["OFF", "ON", "OPTIONAL"], var.mfa_configuration)
    error_message = "mfa_configuration must be OFF, ON, or OPTIONAL."
  }
}

variable "temporary_password_validity_days" {
  description = "Validity window for admin-created temporary passwords."
  type        = number
  default     = 7
}

variable "access_token_validity_minutes" {
  description = "Access-token validity in minutes."
  type        = number
  default     = 60
}

variable "id_token_validity_minutes" {
  description = "ID-token validity in minutes. Vyu validates ID tokens by default."
  type        = number
  default     = 60
}

variable "refresh_token_validity_days" {
  description = "Refresh-token validity in days."
  type        = number
  default     = 1
}

variable "vyu_required_token_use" {
  description = "Token-use claim that Vyu should require when validating Cognito JWTs. The app defaults to ID tokens because they include user attributes and groups."
  type        = string
  default     = "id"

  validation {
    condition     = contains(["id", "access"], var.vyu_required_token_use)
    error_message = "vyu_required_token_use must be id or access."
  }
}

variable "role_groups" {
  description = "Cognito groups that map directly to Vyu roles through IdentityMapper defaults. Lower precedence wins inside Cognito; Vyu still narrows roles through tenant governance."
  type        = map(number)
  default = {
    researcher      = 40
    reviewer        = 30
    workspace_admin = 20
    tenant_admin    = 10
  }
}

variable "saml_identity_providers" {
  description = "Optional enterprise SAML IdPs to federate through Cognito. The map key is the Cognito provider name."
  type = map(object({
    metadata_url      = optional(string)
    metadata_file     = optional(string)
    provider_details  = optional(map(string), {})
    attribute_mapping = optional(map(string), {})
  }))
  default = {}
}

variable "oidc_identity_providers" {
  description = "Optional enterprise OIDC IdPs to federate through Cognito. The map key is the Cognito provider name."
  type = map(object({
    issuer_url         = string
    authorize_url      = string
    token_url          = string
    jwks_uri           = string
    user_info_url      = optional(string)
    authorize_scopes   = optional(list(string), ["openid", "email", "profile"])
    attributes_request_method = optional(string, "GET")
    provider_details   = optional(map(string), {})
    attribute_mapping  = optional(map(string), {})
  }))
  default = {}
}

variable "tags" {
  description = "Additional tags applied through provider default tags."
  type        = map(string)
  default     = {}
}
