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

variable "github_repository" {
  type    = string
  default = "avi9s7/Vyu"
}

variable "github_oidc_audience" {
  type    = string
  default = "sts.amazonaws.com"
}

variable "existing_github_oidc_provider_arn" {
  description = "Optional existing GitHub OIDC provider ARN. When empty, the module creates one."
  type        = string
  default     = ""
}

variable "terraform_state_bucket_name" {
  type    = string
  default = "vyu-terraform-state-example"
}

variable "terraform_state_bucket_arn" {
  type    = string
  default = ""
}

variable "terraform_state_object_key" {
  type    = string
  default = "terraform.tfstate"
}

variable "terraform_state_lock_table_arn" {
  type    = string
  default = ""
}

variable "ecr_repository_names" {
  type = list(string)
}
