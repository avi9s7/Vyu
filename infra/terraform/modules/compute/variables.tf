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

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "security_group_ids" {
  type = object({
    alb       = string
    web       = string
    api       = string
    worker    = string
    migration = string
  })
}

variable "logs_kms_key_arn" {
  type = string
}

variable "data_kms_key_arn" {
  type = string
}

variable "secrets_kms_key_arn" {
  type = string
}

variable "database_master_user_secret_arn" {
  type = string
}

variable "secret_arns" {
  type = map(string)
}

variable "bucket_names" {
  type = object({
    evidence = string
    exports  = string
    audit    = string
  })
}

variable "queue_arns" {
  type = map(string)
}

variable "queue_urls" {
  type = map(string)
}

variable "web_container_port" {
  type    = number
  default = 3000
}

variable "api_container_port" {
  type    = number
  default = 8000
}

variable "image_digests" {
  description = "Immutable OCI image digests keyed by workload."
  type = object({
    web    = string
    api    = string
    worker = string
  })

  validation {
    condition = alltrue([
      can(regex("^sha256:[a-f0-9]{64}$", var.image_digests.web)),
      can(regex("^sha256:[a-f0-9]{64}$", var.image_digests.api)),
      can(regex("^sha256:[a-f0-9]{64}$", var.image_digests.worker)),
    ])
    error_message = "image_digests must be sha256-prefixed lowercase hex digests."
  }
}

variable "ecr_push_role_arns" {
  description = "IAM role ARNs allowed to push images (CI/deploy)."
  type        = list(string)
  default     = []
}

variable "ecr_pull_role_arns" {
  description = "Additional IAM role ARNs allowed to pull images."
  type        = list(string)
  default     = []
}

variable "web_desired_count" {
  type    = number
  default = 2
}

variable "api_desired_count" {
  type    = number
  default = 2
}

variable "worker_min_count" {
  type    = number
  default = 1
}

variable "worker_max_count" {
  type    = number
  default = 6
}

variable "worker_scale_target_queue_depth" {
  type    = number
  default = 100
}

variable "task_cpu" {
  type = object({
    web       = number
    api       = number
    worker    = number
    migration = number
  })
  default = {
    web       = 512
    api       = 1024
    worker    = 1024
    migration = 512
  }
}

variable "task_memory" {
  type = object({
    web       = number
    api       = number
    worker    = number
    migration = number
  })
  default = {
    web       = 1024
    api       = 2048
    worker    = 2048
    migration = 1024
  }
}

variable "ephemeral_storage_gib" {
  type    = number
  default = 21
}

variable "stop_timeout_seconds" {
  type    = number
  default = 30
}
