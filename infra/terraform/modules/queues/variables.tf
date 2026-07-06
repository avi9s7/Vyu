variable "environment" {
  type = string
}

variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "kms_key_arn" {
  type = string
}

variable "alarm_actions" {
  description = "SNS topic ARNs for queue alarms."
  type        = list(string)
  default     = []
}
