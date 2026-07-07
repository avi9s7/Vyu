locals {
  alarm_actions_standard = [aws_sns_topic.alarms.arn]
  alarm_actions_critical = [aws_sns_topic.critical.arn]
}

resource "aws_cloudwatch_metric_alarm" "queue_depth" {
  for_each = var.queue_names

  alarm_name          = "${local.name_prefix}-${each.key}-depth"
  alarm_description   = "Visible messages for ${each.key} queue"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 1000
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions_standard

  dimensions = {
    QueueName = each.value
  }
}

resource "aws_cloudwatch_metric_alarm" "queue_age" {
  for_each = var.queue_names

  alarm_name          = "${local.name_prefix}-${each.key}-oldest-age"
  alarm_description   = "Oldest message age for ${each.key} queue"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateAgeOfOldestMessage"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 3600
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions_critical

  dimensions = {
    QueueName = each.value
  }
}

resource "aws_cloudwatch_metric_alarm" "dlq_messages" {
  for_each = var.dlq_names

  alarm_name          = "${local.name_prefix}-${each.key}-dlq-messages"
  alarm_description   = "Messages visible in ${each.key} DLQ"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions_critical

  dimensions = {
    QueueName = each.value
  }
}

resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  alarm_name          = "${local.name_prefix}-alb-5xx"
  alarm_description   = "ALB target 5xx responses"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 300
  statistic           = "Sum"
  threshold           = 10
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions_critical

  dimensions = {
    LoadBalancer = var.alb_arn_suffix
  }
}

resource "aws_cloudwatch_metric_alarm" "alb_latency" {
  alarm_name          = "${local.name_prefix}-alb-latency"
  alarm_description   = "ALB target response time p95"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "TargetResponseTime"
  namespace           = "AWS/ApplicationELB"
  period              = 300
  extended_statistic  = "p95"
  threshold           = 2
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions_standard

  dimensions = {
    LoadBalancer = var.alb_arn_suffix
  }
}

resource "aws_cloudwatch_metric_alarm" "ecs_cpu" {
  for_each = toset(local.ecs_services)

  alarm_name          = "${local.name_prefix}-ecs-${each.key}-cpu"
  alarm_description   = "ECS ${each.key} CPU utilization"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions_standard

  dimensions = {
    ClusterName = var.ecs_cluster_name
    ServiceName = var.ecs_service_names[each.key]
  }
}

resource "aws_cloudwatch_metric_alarm" "ecs_memory" {
  for_each = toset(local.ecs_services)

  alarm_name          = "${local.name_prefix}-ecs-${each.key}-memory"
  alarm_description   = "ECS ${each.key} memory utilization"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "MemoryUtilization"
  namespace           = "AWS/ECS"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions_standard

  dimensions = {
    ClusterName = var.ecs_cluster_name
    ServiceName = var.ecs_service_names[each.key]
  }
}

resource "aws_cloudwatch_metric_alarm" "rds_connections" {
  alarm_name          = "${local.name_prefix}-rds-connections"
  alarm_description   = "RDS database connections"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "DatabaseConnections"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions_standard

  dimensions = {
    DBInstanceIdentifier = var.database_instance_identifier
  }
}

resource "aws_cloudwatch_metric_alarm" "rds_storage" {
  alarm_name          = "${local.name_prefix}-rds-free-storage"
  alarm_description   = "RDS free storage space"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 2
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 5368709120
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions_critical

  dimensions = {
    DBInstanceIdentifier = var.database_instance_identifier
  }
}

resource "aws_cloudwatch_metric_alarm" "rds_latency" {
  alarm_name          = "${local.name_prefix}-rds-read-latency"
  alarm_description   = "RDS read latency"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ReadLatency"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 0.25
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions_standard

  dimensions = {
    DBInstanceIdentifier = var.database_instance_identifier
  }
}

resource "aws_cloudwatch_metric_alarm" "rds_failover" {
  alarm_name          = "${local.name_prefix}-rds-failover"
  alarm_description   = "RDS failover event"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Failover"
  namespace           = "AWS/RDS"
  period              = 60
  statistic           = "Maximum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions_critical

  dimensions = {
    DBInstanceIdentifier = var.database_instance_identifier
  }
}

resource "aws_cloudwatch_metric_alarm" "cognito_auth_failures" {
  alarm_name          = "${local.name_prefix}-cognito-auth-failures"
  alarm_description   = "Cognito sign-in throttle and failure rate"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "SignInThrottles"
  namespace           = "AWS/Cognito"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions_critical

  dimensions = {
    UserPool = var.cognito_user_pool_id
  }
}

resource "aws_cloudwatch_metric_alarm" "waf_blocks" {
  alarm_name          = "${local.name_prefix}-waf-blocks"
  alarm_description   = "CloudFront WAF blocked requests"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "BlockedRequests"
  namespace           = "AWS/WAFV2"
  period              = 300
  statistic           = "Sum"
  threshold           = 100
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions_standard

  dimensions = {
    WebACL = var.waf_web_acl_name
    Region = "us-east-1"
    Rule   = "ALL"
  }
}

resource "aws_cloudwatch_metric_alarm" "job_failures" {
  alarm_name          = "${local.name_prefix}-job-failures"
  alarm_description   = "Terminal job failures"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "JobFailures"
  namespace           = local.metric_namespace
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions_critical
}

resource "aws_cloudwatch_metric_alarm" "connector_failures" {
  alarm_name          = "${local.name_prefix}-connector-failures"
  alarm_description   = "External connector failures"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ConnectorFailures"
  namespace           = local.metric_namespace
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions_critical
}

resource "aws_cloudwatch_metric_alarm" "model_latency" {
  alarm_name          = "${local.name_prefix}-model-latency"
  alarm_description   = "Model gateway latency p95"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ModelLatencyMs"
  namespace           = local.metric_namespace
  period              = 300
  extended_statistic  = "p95"
  threshold           = 15000
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions_standard
}

resource "aws_cloudwatch_metric_alarm" "model_cost" {
  alarm_name          = "${local.name_prefix}-model-cost"
  alarm_description   = "Model token cost per 5 minutes"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ModelCostUsd"
  namespace           = local.metric_namespace
  period              = 300
  statistic           = "Sum"
  threshold           = 50
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions_standard
}

resource "aws_cloudwatch_metric_alarm" "audit_failures" {
  alarm_name          = "${local.name_prefix}-audit-failures"
  alarm_description   = "Audit pipeline failures"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "AuditFailures"
  namespace           = local.metric_namespace
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions_critical
}

resource "aws_cloudwatch_metric_alarm" "backup_status" {
  alarm_name          = "${local.name_prefix}-backup-storage-anomaly"
  alarm_description   = "RDS backup storage below expected baseline"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 2
  metric_name         = "BackupRetentionPeriodStorageUsed"
  namespace           = "AWS/RDS"
  period              = 86400
  statistic           = "Average"
  threshold           = 1
  treat_missing_data  = "breaching"
  alarm_actions       = local.alarm_actions_critical

  dimensions = {
    DBInstanceIdentifier = var.database_instance_identifier
  }
}

resource "aws_cloudwatch_metric_alarm" "ingestion_malware_infected" {
  alarm_name          = "${local.name_prefix}-ingestion-malware-infected"
  alarm_description   = "Ingestion malware detections"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "IngestionMalwareInfected"
  namespace           = local.metric_namespace
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions_critical
}

resource "aws_cloudwatch_metric_alarm" "ingestion_phi_blocked" {
  alarm_name          = "${local.name_prefix}-ingestion-phi-blocked"
  alarm_description   = "Ingestion suspected PHI blocks"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "IngestionPhiBlocked"
  namespace           = local.metric_namespace
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions_critical
}

resource "aws_cloudwatch_metric_alarm" "ingestion_phi_unknown" {
  alarm_name          = "${local.name_prefix}-ingestion-phi-unknown"
  alarm_description   = "Ingestion uncertain PHI classifications"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "IngestionPhiUnknown"
  namespace           = local.metric_namespace
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions_critical
}

resource "aws_cloudwatch_metric_alarm" "ingestion_scan_errors" {
  alarm_name          = "${local.name_prefix}-ingestion-scan-errors"
  alarm_description   = "Ingestion screening failures"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "IngestionScanErrors"
  namespace           = local.metric_namespace
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions_standard
}

resource "aws_cloudwatch_metric_alarm" "ingestion_parser_failures" {
  alarm_name          = "${local.name_prefix}-ingestion-parser-failures"
  alarm_description   = "Ingestion parser failures"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "IngestionParserFailures"
  namespace           = local.metric_namespace
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions_standard
}

resource "aws_cloudwatch_metric_alarm" "ingestion_ready_latency" {
  alarm_name          = "${local.name_prefix}-ingestion-ready-latency"
  alarm_description   = "Ingestion ready latency p95"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "IngestionReadyLatencyMs"
  namespace           = local.metric_namespace
  period              = 300
  extended_statistic  = "p95"
  threshold           = 900000
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions_standard
}

resource "aws_cloudwatch_metric_alarm" "ingestion_quarantine_age" {
  alarm_name          = "${local.name_prefix}-ingestion-quarantine-age"
  alarm_description   = "Blocked quarantine object age p95"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "IngestionQuarantineAgeSeconds"
  namespace           = local.metric_namespace
  period              = 3600
  extended_statistic  = "p95"
  threshold           = 604800
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions_standard
}

resource "aws_cloudwatch_metric_alarm" "pubmed_probe_failures" {
  alarm_name          = "${local.name_prefix}-pubmed-probe-failures"
  alarm_description   = "Repeated PubMed staging probe failures"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "PubMedProbeFailures"
  namespace           = local.metric_namespace
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions_critical
}
