terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.81.0, < 7.0.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = merge(
      {
        Application = "Vyu"
        ManagedBy   = "Terraform"
        Module      = "identity-access-cognito"
      },
      var.tags,
    )
  }
}
