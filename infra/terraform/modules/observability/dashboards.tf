resource "aws_cloudwatch_dashboard" "operations" {
  dashboard_name = "${local.name_prefix}-operations"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "ALB 5xx"
          region = var.aws_region
          metrics = [
            ["AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", "LoadBalancer", var.alb_arn_suffix],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "ALB latency p95"
          region = var.aws_region
          metrics = [
            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", var.alb_arn_suffix, { stat = "p95" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 8
        height = 6
        properties = {
          title  = "ECS CPU"
          region = var.aws_region
          metrics = [
            for service in local.ecs_services : [
              "AWS/ECS",
              "CPUUtilization",
              "ClusterName",
              var.ecs_cluster_name,
              "ServiceName",
              var.ecs_service_names[service],
            ]
          ]
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 6
        width  = 8
        height = 6
        properties = {
          title  = "ECS memory"
          region = var.aws_region
          metrics = [
            for service in local.ecs_services : [
              "AWS/ECS",
              "MemoryUtilization",
              "ClusterName",
              var.ecs_cluster_name,
              "ServiceName",
              var.ecs_service_names[service],
            ]
          ]
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 6
        width  = 8
        height = 6
        properties = {
          title  = "RDS connections / storage"
          region = var.aws_region
          metrics = [
            ["AWS/RDS", "DatabaseConnections", "DBInstanceIdentifier", var.database_instance_identifier],
            [".", "FreeStorageSpace", ".", "."],
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 12
        width  = 12
        height = 6
        properties = {
          title  = "Queue depth"
          region = var.aws_region
          metrics = [
            for workload, queue_name in var.queue_names : [
              "AWS/SQS",
              "ApproximateNumberOfMessagesVisible",
              "QueueName",
              queue_name,
            ]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 12
        width  = 12
        height = 6
        properties = {
          title  = "Queue oldest age / DLQ"
          region = var.aws_region
          metrics = concat(
            [
              for workload, queue_name in var.queue_names : [
                "AWS/SQS",
                "ApproximateAgeOfOldestMessage",
                "QueueName",
                queue_name,
              ]
            ],
            [
              for workload, queue_name in var.dlq_names : [
                "AWS/SQS",
                "ApproximateNumberOfMessagesVisible",
                "QueueName",
                queue_name,
              ]
            ],
          )
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 18
        width  = 8
        height = 6
        properties = {
          title  = "Cognito auth throttles"
          region = var.aws_region
          metrics = [
            ["AWS/Cognito", "SignInThrottles", "UserPool", var.cognito_user_pool_id],
          ]
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 18
        width  = 8
        height = 6
        properties = {
          title  = "WAF blocked requests"
          region = "us-east-1"
          metrics = [
            ["AWS/WAFV2", "BlockedRequests", "WebACL", var.waf_web_acl_name, "Region", "us-east-1", "Rule", "ALL"],
          ]
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 18
        width  = 8
        height = 6
        properties = {
          title  = "Application signals"
          region = var.aws_region
          metrics = [
            [local.metric_namespace, "JobFailures"],
            [".", "ConnectorFailures"],
            [".", "AuditFailures"],
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 24
        width  = 12
        height = 6
        properties = {
          title  = "Model latency and cost"
          region = var.aws_region
          metrics = [
            [local.metric_namespace, "ModelLatencyMs", { stat = "p95" }],
            [".", "ModelCostUsd", { stat = "Sum" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 24
        width  = 12
        height = 6
        properties = {
          title  = "RDS backup storage"
          region = var.aws_region
          metrics = [
            ["AWS/RDS", "BackupRetentionPeriodStorageUsed", "DBInstanceIdentifier", var.database_instance_identifier],
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 30
        width  = 8
        height = 6
        properties = {
          title  = "Ingestion uploads and bytes"
          region = var.aws_region
          metrics = [
            [local.metric_namespace, "IngestionUploads", { stat = "Sum" }],
            [".", "IngestionBytes", { stat = "Sum" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 30
        width  = 8
        height = 6
        properties = {
          title  = "Ingestion scan latency p95"
          region = var.aws_region
          metrics = [
            [local.metric_namespace, "IngestionScanLatencyMs", { stat = "p95" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 30
        width  = 8
        height = 6
        properties = {
          title  = "Ingestion screening blocks"
          region = var.aws_region
          metrics = [
            [local.metric_namespace, "IngestionMalwareInfected", { stat = "Sum" }],
            [".", "IngestionPhiBlocked", { stat = "Sum" }],
            [".", "IngestionPhiUnknown", { stat = "Sum" }],
            [".", "IngestionScanErrors", { stat = "Sum" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 36
        width  = 8
        height = 6
        properties = {
          title  = "Ingestion parser failures"
          region = var.aws_region
          metrics = [
            [local.metric_namespace, "IngestionParserFailures", { stat = "Sum" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 36
        width  = 8
        height = 6
        properties = {
          title  = "Ingestion ready latency p95"
          region = var.aws_region
          metrics = [
            [local.metric_namespace, "IngestionReadyLatencyMs", { stat = "p95" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 36
        width  = 8
        height = 6
        properties = {
          title  = "Ingestion duplicates and quarantine age"
          region = var.aws_region
          metrics = [
            [local.metric_namespace, "IngestionDuplicates", { stat = "Sum" }],
            [".", "IngestionQuarantineAgeSeconds", { stat = "p95" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 42
        width  = 12
        height = 6
        properties = {
          title  = "PubMed probe failures"
          region = var.aws_region
          metrics = [
            [local.metric_namespace, "PubMedProbeFailures", { stat = "Sum" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 42
        width  = 12
        height = 6
        properties = {
          title  = "PubMed probe latency p95"
          region = var.aws_region
          metrics = [
            [local.metric_namespace, "PubMedProbeLatencyMs", { stat = "p95" }],
          ]
        }
      },
    ]
  })
}
