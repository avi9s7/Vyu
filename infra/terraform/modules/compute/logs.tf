resource "aws_cloudwatch_log_group" "service" {
  for_each = toset(local.services)

  name              = "/vyu/${var.environment}/${each.key}"
  retention_in_days = local.log_retention_in_days
  kms_key_id        = var.logs_kms_key_arn

  tags = {
    Name        = "vyu-${var.environment}-${each.key}"
    Environment = var.environment
    Workload    = each.key
  }
}
