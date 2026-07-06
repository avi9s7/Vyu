resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids = concat(
    [aws_route_table.public.id],
    [for table in aws_route_table.private : table.id],
    [aws_route_table.database.id],
  )

  tags = {
    Name        = "vyu-${var.environment}-s3"
    Environment = var.environment
  }
}

resource "aws_security_group" "vpc_endpoints" {
  name        = "vyu-${var.environment}-vpc-endpoints"
  description = "Interface VPC endpoints"
  vpc_id      = aws_vpc.this.id

  tags = {
    Name        = "vyu-${var.environment}-vpc-endpoints"
    Environment = var.environment
  }
}

resource "aws_vpc_security_group_ingress_rule" "vpc_endpoints_https_from_private" {
  for_each = local.endpoint_client_security_groups

  security_group_id            = aws_security_group.vpc_endpoints.id
  referenced_security_group_id = each.value
  description                  = "HTTPS from ${each.key} tasks"
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
}

locals {
  endpoint_client_security_groups = {
    alb       = aws_security_group.alb.id
    web       = aws_security_group.web.id
    api       = aws_security_group.api.id
    worker    = aws_security_group.worker.id
    migration = aws_security_group.migration.id
  }

  interface_endpoints = {
    ecr_api = "com.amazonaws.${var.aws_region}.ecr.api"
    ecr_dkr = "com.amazonaws.${var.aws_region}.ecr.dkr"
    logs    = "com.amazonaws.${var.aws_region}.logs"
    secrets = "com.amazonaws.${var.aws_region}.secretsmanager"
    sqs     = "com.amazonaws.${var.aws_region}.sqs"
    kms     = "com.amazonaws.${var.aws_region}.kms"
    sts     = "com.amazonaws.${var.aws_region}.sts"
  }
}

resource "aws_vpc_endpoint" "interface" {
  for_each = local.interface_endpoints

  vpc_id              = aws_vpc.this.id
  service_name        = each.value
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [for subnet in aws_subnet.private : subnet.id]
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = {
    Name        = "vyu-${var.environment}-${each.key}"
    Environment = var.environment
  }
}
