resource "aws_ssm_parameter" "otel_collector_config" {
  name = "/vyu/${var.environment}/otel-collector/config"
  type = "String"
  value = yamlencode({
    receivers = {
      otlp = {
        protocols = {
          grpc = {
            endpoint = "0.0.0.0:4317"
          }
          http = {
            endpoint = "0.0.0.0:4318"
          }
        }
      }
    }
    processors = {
      batch = {}
      resource = {
        attributes = [
          {
            key    = "service.environment"
            value  = var.environment
            action = "upsert"
          },
        ]
      }
    }
    exporters = {
      awsxray = {
        region = var.aws_region
      }
      awsemf = {
        region                  = var.aws_region
        namespace               = local.metric_namespace
        log_group_name          = aws_cloudwatch_log_group.otel_collector.name
        dimension_rollup_option = "NoDimensionRollup"
      }
      awscloudwatchlogs = {
        log_group_name  = aws_cloudwatch_log_group.otel_collector.name
        log_stream_name = "collector"
        region          = var.aws_region
      }
    }
    service = {
      pipelines = {
        traces = {
          receivers  = ["otlp"]
          processors = ["batch", "resource"]
          exporters  = ["awsxray"]
        }
        metrics = {
          receivers  = ["otlp"]
          processors = ["batch", "resource"]
          exporters  = ["awsemf"]
        }
        logs = {
          receivers  = ["otlp"]
          processors = ["batch"]
          exporters  = ["awscloudwatchlogs"]
        }
      }
    }
  })

  tags = {
    Name        = "${local.name_prefix}-otel-collector-config"
    Environment = var.environment
  }
}
