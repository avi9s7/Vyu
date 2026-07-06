variable "environment" {
  type = string
}

variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "single_nat_gateway" {
  type    = bool
  default = false
}

variable "identity_callback_urls" {
  type = list(string)
}

variable "identity_logout_urls" {
  type = list(string)
}

variable "identity_cognito_domain_prefix" {
  type = string
}

variable "identity_resource_server_identifier" {
  type = string
}

variable "identity_saml_identity_providers" {
  type = map(object({
    metadata_url      = optional(string)
    metadata_file     = optional(string)
    provider_details  = optional(map(string), {})
    attribute_mapping = optional(map(string), {})
  }))
  default = {}
}

variable "identity_oidc_identity_providers" {
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

variable "compute_image_digests" {
  type = object({
    web    = string
    api    = string
    worker = string
  })
  default = {
    web    = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    api    = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    worker = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
  }
}

variable "compute_ecr_push_role_arns" {
  type    = list(string)
  default = []
}

variable "edge_primary_domain_name" {
  type = string
}

variable "edge_route53_zone_id" {
  type = string
}
