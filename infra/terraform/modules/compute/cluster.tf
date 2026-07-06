resource "aws_ecs_cluster" "this" {
  name = "vyu-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name        = "vyu-${var.environment}"
    Environment = var.environment
  }
}
