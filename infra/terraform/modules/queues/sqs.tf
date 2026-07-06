resource "aws_sqs_queue" "dlq" {
  for_each = local.workloads

  name                       = "vyu-${var.environment}-${each.key}-dlq"
  message_retention_seconds  = 1209600
  kms_master_key_id          = var.kms_key_arn
  receive_wait_time_seconds  = 20

  tags = {
    Name        = "vyu-${var.environment}-${each.key}-dlq"
    Environment = var.environment
    Workload    = each.key
  }
}

resource "aws_sqs_queue" "workload" {
  for_each = local.workloads

  name                       = "vyu-${var.environment}-${each.key}"
  visibility_timeout_seconds = each.value.visibility_timeout_seconds
  message_retention_seconds  = 1209600
  kms_master_key_id          = var.kms_key_arn
  receive_wait_time_seconds  = 20

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[each.key].arn
    maxReceiveCount     = 5
  })

  tags = {
    Name        = "vyu-${var.environment}-${each.key}"
    Environment = var.environment
    Workload    = each.key
  }
}

resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  for_each = local.workloads

  queue_url = aws_sqs_queue.dlq[each.key].id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.workload[each.key].arn]
  })
}
