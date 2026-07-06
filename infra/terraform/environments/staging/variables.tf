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
