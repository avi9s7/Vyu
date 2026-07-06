output "queue_urls" {
  value = { for key, queue in aws_sqs_queue.workload : key => queue.url }
}

output "queue_arns" {
  value = { for key, queue in aws_sqs_queue.workload : key => queue.arn }
}

output "queue_names" {
  value = { for key, queue in aws_sqs_queue.workload : key => queue.name }
}

output "dlq_arns" {
  value = { for key, queue in aws_sqs_queue.dlq : key => queue.arn }
}

output "dlq_names" {
  value = { for key, queue in aws_sqs_queue.dlq : key => queue.name }
}
