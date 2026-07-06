resource "aws_appautoscaling_target" "worker" {
  max_capacity       = var.worker_max_count
  min_capacity       = var.worker_min_count
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.worker.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

locals {
  ingestion_queue_name = element(split("/", var.queue_urls["ingestion"]), length(split("/", var.queue_urls["ingestion"])) - 1)
}

resource "aws_appautoscaling_policy" "worker_queue_depth" {
  name               = "vyu-${var.environment}-worker-queue-depth"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.worker.resource_id
  scalable_dimension = aws_appautoscaling_target.worker.scalable_dimension
  service_namespace  = aws_appautoscaling_target.worker.service_namespace

  target_tracking_scaling_policy_configuration {
    target_value = var.worker_scale_target_queue_depth

    customized_metric_specification {
      metric_name = "ApproximateNumberOfMessagesVisible"
      namespace   = "AWS/SQS"
      statistic   = "Average"

      dimensions {
        name  = "QueueName"
        value = local.ingestion_queue_name
      }
    }

    scale_in_cooldown  = 120
    scale_out_cooldown = 60
  }
}
