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

resource "aws_lb_listener" "https" {
  count = var.alb_certificate_arn != "" ? 1 : 0

  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.alb_certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web.arn
  }
}

resource "aws_lb_listener_rule" "api" {
  count = var.alb_certificate_arn != "" ? 1 : 0

  listener_arn = aws_lb_listener.https[0].arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    path_pattern {
      values = ["/v1/*", "/docs*", "/openapi.json"]
    }
  }
}
