provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Application = "vyu"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
