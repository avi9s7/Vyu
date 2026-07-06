data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition
  name_prefix = "vyu-${var.environment}"

  github_oidc_provider_arn = coalesce(
    var.existing_github_oidc_provider_arn,
    try(aws_iam_openid_connect_provider.github[0].arn, null),
  )

  state_bucket_arn = var.terraform_state_bucket_arn != "" ? var.terraform_state_bucket_arn : "arn:${local.partition}:s3:::${var.terraform_state_bucket_name}"
  state_object_arn = "${local.state_bucket_arn}/${var.terraform_state_object_key}"

  ecr_repository_arns = [
    for repository in var.ecr_repository_names :
    "arn:${local.partition}:ecr:${var.aws_region}:${local.account_id}:repository/${repository}"
  ]

  ecs_cluster_arn = "arn:${local.partition}:ecs:${var.aws_region}:${local.account_id}:cluster/${local.name_prefix}"
  ecs_service_arns = [
    for service in ["web", "api", "worker"] :
    "arn:${local.partition}:ecs:${var.aws_region}:${local.account_id}:service/${local.name_prefix}/${local.name_prefix}-${service}"
  ]
  migration_task_definition_arn = "arn:${local.partition}:ecs:${var.aws_region}:${local.account_id}:task-definition/${local.name_prefix}-migration:*"
}
