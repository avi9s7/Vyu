output "alarm_topic_arn" {
  value = aws_sns_topic.alarms.arn
}

output "critical_alarm_topic_arn" {
  value = aws_sns_topic.critical.arn
}

output "otel_collector_config_parameter_name" {
  value = aws_ssm_parameter.otel_collector_config.name
}

output "otel_collector_log_group_name" {
  value = aws_cloudwatch_log_group.otel_collector.name
}

output "dashboard_name" {
  value = aws_cloudwatch_dashboard.operations.dashboard_name
}

output "monitored_log_group_names" {
  value = var.service_log_group_names
}
