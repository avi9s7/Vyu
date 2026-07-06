variable "environment" {
  type = string
}

variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "vpc_id" {
  type = string
}

variable "database_subnet_ids" {
  type = list(string)
}

variable "database_security_group_id" {
  type = string
}

variable "data_kms_key_arn" {
  type = string
}

variable "audit_kms_key_arn" {
  type = string
}

variable "secrets_kms_key_arn" {
  type = string
}

variable "postgres_engine_version" {
  type    = string
  default = "17.4"
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.medium"
}
