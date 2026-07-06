data "aws_caller_identity" "current" {}

locals {
  is_production = var.environment == "prod"
  name_suffix   = data.aws_caller_identity.current.account_id

  bucket_names = {
    evidence = "vyu-${var.environment}-evidence-${local.name_suffix}"
    exports  = "vyu-${var.environment}-exports-${local.name_suffix}"
    audit    = "vyu-${var.environment}-audit-${local.name_suffix}"
    access_logs = "vyu-${var.environment}-access-logs-${local.name_suffix}"
  }

  secret_names = {
    database_connection = "vyu/${var.environment}/database/connection"
    providers           = "vyu/${var.environment}/providers"
  }

  pilot_recovery_targets = {
    rpo_minutes = 15
    rto_hours   = 4
  }
}
