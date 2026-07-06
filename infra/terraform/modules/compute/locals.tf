data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  is_production = var.environment == "prod"
  account_id    = data.aws_caller_identity.current.account_id
  region        = data.aws_region.current.region

  services = ["web", "api", "worker", "migration"]

  ecr_repositories = {
    web    = "vyu-${var.environment}-web"
    api    = "vyu-${var.environment}-api"
    worker = "vyu-${var.environment}-worker"
  }

  log_retention_in_days = local.is_production ? 90 : 30

  image_repositories = {
    web       = aws_ecr_repository.this["web"].repository_url
    api       = aws_ecr_repository.this["api"].repository_url
    worker    = aws_ecr_repository.this["worker"].repository_url
    migration = aws_ecr_repository.this["api"].repository_url
  }

  common_task_tags = {
    Environment = var.environment
    ManagedBy   = "terraform"
    Module      = "compute"
  }
}
