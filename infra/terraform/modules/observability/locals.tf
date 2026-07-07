locals {
  is_production    = var.environment == "prod"
  name_prefix      = "vyu-${var.environment}"
  metric_namespace = "VYU/${var.environment}"

  ecs_services           = ["web", "api", "worker"]
  application_log_groups = var.service_log_group_names

  dashboard_widgets = [
    "alb_5xx",
    "alb_latency",
    "ecs_cpu",
    "ecs_memory",
    "rds_connections",
    "rds_storage",
    "rds_latency",
    "queue_depth",
    "queue_age",
    "dlq_messages",
    "cognito_auth_failures",
    "waf_blocks",
    "job_failures",
    "connector_failures",
    "model_latency",
    "model_cost",
    "audit_failures",
    "backup_status",
    "ingestion_uploads",
    "ingestion_scan_latency",
    "ingestion_malware_infected",
    "ingestion_phi_blocked",
    "ingestion_parser_failures",
    "ingestion_ready_latency",
    "ingestion_duplicates",
    "ingestion_quarantine_age",
    "pubmed_probe_failures",
    "pubmed_probe_latency",
  ]
}
