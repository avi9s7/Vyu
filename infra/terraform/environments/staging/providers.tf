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

provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = {
      Application = "vyu"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
