terraform {
  required_version = ">= 1.9, < 2.0"

  backend "s3" {}

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.80, < 7.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "< 4"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "< 5"
    }
  }
}
