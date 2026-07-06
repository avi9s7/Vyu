output "cluster_arn" {
  value = aws_ecs_cluster.this.arn
}

output "cluster_name" {
  value = aws_ecs_cluster.this.name
}

output "ecr_repository_urls" {
  value = { for key, repo in aws_ecr_repository.this : key => repo.repository_url }
}

output "execution_role_arns" {
  value = { for key, role in aws_iam_role.execution : key => role.arn }
}

output "task_role_arns" {
  value = { for key, role in aws_iam_role.task : key => role.arn }
}

output "service_names" {
  value = {
    web    = aws_ecs_service.web.name
    api    = aws_ecs_service.api.name
    worker = aws_ecs_service.worker.name
  }
}

output "migration_task_definition_arn" {
  value = aws_ecs_task_definition.migration.arn
}

output "alb_arn" {
  value = aws_lb.this.arn
}

output "alb_dns_name" {
  value = aws_lb.this.dns_name
}

output "target_group_arns" {
  value = {
    web = aws_lb_target_group.web.arn
    api = aws_lb_target_group.api.arn
  }
}

output "log_group_names" {
  value = { for key, group in aws_cloudwatch_log_group.service : key => group.name }
}
