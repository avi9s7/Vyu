variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "state_bucket_name" {
  type        = string
  description = "Globally unique S3 bucket for Terraform remote state."
}

variable "lock_table_name" {
  type        = string
  description = "DynamoDB table used for Terraform state locking."
}

variable "project_name" {
  type    = string
  default = "vyu"
}
