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

variable "logs_kms_key_arn" {
  type = string
}

variable "alb_arn_suffix" {
  description = "Load balancer ARN suffix used for ALB CloudWatch metrics."
  type        = string
}

variable "ecs_cluster_name" {
  type = string
}

variable "ecs_service_names" {
  type = object({
    web    = string
    api    = string
    worker = string
  })
}

variable "database_instance_identifier" {
  type = string
}

variable "cognito_user_pool_id" {
  type = string
}

variable "waf_web_acl_name" {
  type = string
}

variable "service_log_group_names" {
  description = "Application CloudWatch log group names keyed by workload."
  type        = map(string)
}

variable "queue_names" {
  description = "SQS workload queue names keyed by workload."
  type        = map(string)
}

variable "dlq_names" {
  description = "SQS dead-letter queue names keyed by workload."
  type        = map(string)
}

variable "on_call_email_addresses" {
  description = "Email addresses subscribed to critical alarm notifications."
  type        = list(string)
  default     = []
}

variable "critical_alarm_owner_acknowledged" {
  description = "Must be true before applying production critical alarms."
  type        = bool
  default     = false

  validation {
    condition     = var.environment != "prod" || var.critical_alarm_owner_acknowledged
    error_message = "Set critical_alarm_owner_acknowledged = true for production critical alarms."
  }
}
