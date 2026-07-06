data "aws_ec2_managed_prefix_list" "cloudfront_origin_facing" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

resource "aws_security_group" "alb" {
  name        = "vyu-${var.environment}-alb"
  description = "Allow HTTPS from CloudFront to the ALB"
  vpc_id      = aws_vpc.this.id

  tags = {
    Name        = "vyu-${var.environment}-alb"
    Environment = var.environment
  }
}

resource "aws_vpc_security_group_ingress_rule" "alb_https_from_cloudfront" {
  security_group_id = aws_security_group.alb.id
  description       = "HTTPS from CloudFront origin-facing prefix list"

  from_port      = 443
  to_port        = 443
  ip_protocol    = "tcp"
  prefix_list_id = data.aws_ec2_managed_prefix_list.cloudfront_origin_facing.id
}

resource "aws_vpc_security_group_egress_rule" "alb_to_web" {
  security_group_id            = aws_security_group.alb.id
  description                  = "Forward HTTPS to web tasks"
  referenced_security_group_id = aws_security_group.web.id
  from_port                    = var.web_container_port
  to_port                      = var.web_container_port
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "alb_to_api" {
  security_group_id            = aws_security_group.alb.id
  description                  = "Forward HTTPS to API tasks"
  referenced_security_group_id = aws_security_group.api.id
  from_port                    = var.api_container_port
  to_port                      = var.api_container_port
  ip_protocol                  = "tcp"
}

resource "aws_security_group" "web" {
  name        = "vyu-${var.environment}-web"
  description = "Web ECS tasks"
  vpc_id      = aws_vpc.this.id

  tags = {
    Name        = "vyu-${var.environment}-web"
    Environment = var.environment
  }
}

resource "aws_vpc_security_group_ingress_rule" "web_from_alb" {
  security_group_id            = aws_security_group.web.id
  referenced_security_group_id = aws_security_group.alb.id
  description                  = "Container port from ALB"
  from_port                    = var.web_container_port
  to_port                      = var.web_container_port
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "web_to_api" {
  security_group_id            = aws_security_group.web.id
  referenced_security_group_id = aws_security_group.api.id
  description                  = "Web BFF to API"
  from_port                    = var.api_container_port
  to_port                      = var.api_container_port
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "web_https_egress" {
  security_group_id = aws_security_group.web.id
  description       = "Approved HTTPS egress"
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

resource "aws_security_group" "api" {
  name        = "vyu-${var.environment}-api"
  description = "API ECS tasks"
  vpc_id      = aws_vpc.this.id

  tags = {
    Name        = "vyu-${var.environment}-api"
    Environment = var.environment
  }
}

resource "aws_vpc_security_group_ingress_rule" "api_from_alb" {
  security_group_id            = aws_security_group.api.id
  referenced_security_group_id = aws_security_group.alb.id
  description                  = "API port from ALB"
  from_port                    = var.api_container_port
  to_port                      = var.api_container_port
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "api_from_web" {
  security_group_id            = aws_security_group.api.id
  referenced_security_group_id = aws_security_group.web.id
  description                  = "API port from web BFF"
  from_port                    = var.api_container_port
  to_port                      = var.api_container_port
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "api_to_database" {
  security_group_id            = aws_security_group.api.id
  referenced_security_group_id = aws_security_group.database.id
  description                  = "PostgreSQL"
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "api_https_egress" {
  security_group_id = aws_security_group.api.id
  description       = "Approved HTTPS egress"
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

resource "aws_security_group" "worker" {
  name        = "vyu-${var.environment}-worker"
  description = "Worker ECS tasks"
  vpc_id      = aws_vpc.this.id

  tags = {
    Name        = "vyu-${var.environment}-worker"
    Environment = var.environment
  }
}

resource "aws_vpc_security_group_egress_rule" "worker_to_database" {
  security_group_id            = aws_security_group.worker.id
  referenced_security_group_id = aws_security_group.database.id
  description                  = "PostgreSQL"
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "worker_https_egress" {
  security_group_id = aws_security_group.worker.id
  description       = "Approved HTTPS egress"
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
}

resource "aws_security_group" "migration" {
  name        = "vyu-${var.environment}-migration"
  description = "One-off migration tasks"
  vpc_id      = aws_vpc.this.id

  tags = {
    Name        = "vyu-${var.environment}-migration"
    Environment = var.environment
  }
}

resource "aws_vpc_security_group_egress_rule" "migration_to_database" {
  security_group_id            = aws_security_group.migration.id
  referenced_security_group_id = aws_security_group.database.id
  description                  = "PostgreSQL"
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

resource "aws_security_group" "database" {
  name        = "vyu-${var.environment}-database"
  description = "RDS PostgreSQL"
  vpc_id      = aws_vpc.this.id

  tags = {
    Name        = "vyu-${var.environment}-database"
    Environment = var.environment
  }
}

resource "aws_vpc_security_group_ingress_rule" "database_from_api" {
  security_group_id            = aws_security_group.database.id
  referenced_security_group_id = aws_security_group.api.id
  description                  = "PostgreSQL from API"
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "database_from_worker" {
  security_group_id            = aws_security_group.database.id
  referenced_security_group_id = aws_security_group.worker.id
  description                  = "PostgreSQL from worker"
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "database_from_migration" {
  security_group_id            = aws_security_group.database.id
  referenced_security_group_id = aws_security_group.migration.id
  description                  = "PostgreSQL from migration"
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}
