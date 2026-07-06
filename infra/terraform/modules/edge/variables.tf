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

variable "primary_domain_name" {
  description = "Primary application hostname served by CloudFront."
  type        = string
}

variable "route53_zone_id" {
  description = "Route 53 hosted zone ID for DNS validation and alias records."
  type        = string
}

variable "alb_arn" {
  type = string
}

variable "alb_dns_name" {
  type = string
}

variable "target_group_arns" {
  type = object({
    web = string
    api = string
  })
}

variable "web_container_port" {
  type    = number
  default = 3000
}

variable "api_container_port" {
  type    = number
  default = 8000
}

variable "evidence_bucket_name" {
  type = string
}

variable "access_logs_bucket_domain_name" {
  description = "Regional domain name of the access-logs bucket for CloudFront logging."
  type        = string
}

variable "api_body_size_limit_bytes" {
  description = "Maximum request body size allowed through WAF for API paths."
  type        = number
  default     = 8192
}

variable "waf_rate_limit" {
  description = "Per-IP request rate limit over a 5-minute window."
  type        = number
  default     = 2000
}
