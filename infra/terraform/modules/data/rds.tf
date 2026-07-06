resource "aws_db_subnet_group" "this" {
  name       = "vyu-${var.environment}-database"
  subnet_ids = var.database_subnet_ids

  tags = {
    Name        = "vyu-${var.environment}-database"
    Environment = var.environment
  }
}

resource "aws_db_parameter_group" "postgres" {
  name   = "vyu-${var.environment}-postgres17"
  family = "postgres17"

  parameter {
    name  = "statement_timeout"
    value = "15000"
  }

  parameter {
    name  = "idle_in_transaction_session_timeout"
    value = "60000"
  }

  tags = {
    Name        = "vyu-${var.environment}-postgres17"
    Environment = var.environment
  }
}

resource "aws_db_instance" "postgres" {
  identifier = "vyu-${var.environment}-postgres"

  engine         = "postgres"
  engine_version = var.postgres_engine_version
  instance_class = var.db_instance_class

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [var.database_security_group_id]
  parameter_group_name   = aws_db_parameter_group.postgres.name

  allocated_storage     = local.is_production ? 100 : 20
  max_allocated_storage = local.is_production ? 500 : 100
  storage_type          = "gp3"
  storage_encrypted     = true
  kms_key_id            = var.data_kms_key_arn

  multi_az            = local.is_production
  publicly_accessible = false

  db_name  = "vyu"
  username = "vyu_admin"

  manage_master_user_password   = true
  master_user_secret_kms_key_id = var.secrets_kms_key_arn

  backup_retention_period   = local.is_production ? 35 : 7
  backup_window             = "19:00-20:00"
  copy_tags_to_snapshot     = true
  maintenance_window        = "sun:20:00-sun:21:00"
  deletion_protection       = local.is_production
  skip_final_snapshot       = !local.is_production
  final_snapshot_identifier = local.is_production ? "vyu-${var.environment}-postgres-final" : null

  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  monitoring_interval             = local.is_production ? 60 : 0
  monitoring_role_arn             = local.is_production ? aws_iam_role.rds_enhanced_monitoring[0].arn : null
  performance_insights_enabled    = local.is_production
  performance_insights_kms_key_id = local.is_production ? var.data_kms_key_arn : null

  tags = {
    Name        = "vyu-${var.environment}-postgres"
    Environment = var.environment
  }
}

resource "aws_iam_role" "rds_enhanced_monitoring" {
  count = local.is_production ? 1 : 0

  name = "vyu-${var.environment}-rds-monitoring"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "monitoring.rds.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "rds_enhanced_monitoring" {
  count = local.is_production ? 1 : 0

  role       = aws_iam_role.rds_enhanced_monitoring[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}
