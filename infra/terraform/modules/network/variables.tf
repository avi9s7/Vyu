variable "environment" {
  type = string
}

variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "single_nat_gateway" {
  description = "Use one NAT gateway for cost-sensitive non-production environments."
  type        = bool
  default     = false
}

variable "web_container_port" {
  type    = number
  default = 3000
}

variable "api_container_port" {
  type    = number
  default = 8000
}
