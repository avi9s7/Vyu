resource "aws_lb" "this" {
  name               = "vyu-${var.environment}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.security_group_ids.alb]
  subnets            = var.public_subnet_ids

  enable_deletion_protection = local.is_production

  tags = {
    Name        = "vyu-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_lb_target_group" "web" {
  name        = "vyu-${var.environment}-web"
  port        = var.web_container_port
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    enabled             = true
    path                = "/api/health"
    matcher             = "200"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 15
    timeout             = 5
  }

  tags = {
    Name        = "vyu-${var.environment}-web"
    Environment = var.environment
  }
}

resource "aws_lb_target_group" "api" {
  name        = "vyu-${var.environment}-api"
  port        = var.api_container_port
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    enabled             = true
    path                = "/v1/health/live"
    matcher             = "200"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 15
    timeout             = 5
  }

  tags = {
    Name        = "vyu-${var.environment}-api"
    Environment = var.environment
  }
}
