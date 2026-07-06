resource "aws_sns_topic" "alarms" {
  name              = "${local.name_prefix}-alarms"
  kms_master_key_id = var.logs_kms_key_arn

  tags = {
    Name        = "${local.name_prefix}-alarms"
    Environment = var.environment
    Severity    = "standard"
  }
}

resource "aws_sns_topic" "critical" {
  name              = "${local.name_prefix}-critical-alarms"
  kms_master_key_id = var.logs_kms_key_arn

  tags = {
    Name        = "${local.name_prefix}-critical-alarms"
    Environment = var.environment
    Severity    = "critical"
  }
}

resource "aws_sns_topic_subscription" "critical_email" {
  for_each = toset(var.on_call_email_addresses)

  topic_arn = aws_sns_topic.critical.arn
  protocol  = "email"
  endpoint  = each.value
}

resource "aws_cloudwatch_log_group" "otel_collector" {
  name              = "/vyu/${var.environment}/otel-collector"
  retention_in_days = local.is_production ? 90 : 30
  kms_key_id        = var.logs_kms_key_arn

  tags = {
    Name        = "${local.name_prefix}-otel-collector"
    Environment = var.environment
    Workload    = "otel-collector"
  }
}
