resource "aws_cloudwatch_metric_alarm" "queue_depth" {
  for_each = local.workloads

  alarm_name          = "vyu-${var.environment}-${each.key}-depth"
  alarm_description   = "Visible messages for ${each.key} queue"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 1000
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.workload[each.key].name
  }

  alarm_actions = var.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "queue_age" {
  for_each = local.workloads

  alarm_name          = "vyu-${var.environment}-${each.key}-oldest-age"
  alarm_description   = "Oldest message age for ${each.key} queue"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateAgeOfOldestMessage"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 3600
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.workload[each.key].name
  }

  alarm_actions = var.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "dlq_messages" {
  for_each = local.workloads

  alarm_name          = "vyu-${var.environment}-${each.key}-dlq-messages"
  alarm_description   = "Messages visible in ${each.key} DLQ"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.dlq[each.key].name
  }

  alarm_actions = var.alarm_actions
}
