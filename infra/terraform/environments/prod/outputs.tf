output "github_plan_role_arn" {
  description = "Repository variable AWS_PLAN_ROLE_ARN when planning prod (optional; dev role used by default in CI)."
  value       = module.github_oidc.plan_role_arn
}

output "github_apply_role_arn" {
  description = "GitHub environment variable AWS_APPLY_ROLE_ARN for deploy workflow."
  value       = module.github_oidc.apply_role_arn
}

output "github_build_role_arn" {
  description = "GitHub environment variable AWS_BUILD_ROLE_ARN for deploy workflow."
  value       = module.github_oidc.build_role_arn
}

output "private_subnet_ids_csv" {
  description = "GitHub environment variable AWS_PRIVATE_SUBNET_IDS (comma-separated)."
  value       = join(",", module.network.private_subnet_ids)
}

output "migration_security_group_id" {
  description = "GitHub environment variable AWS_MIGRATION_SECURITY_GROUP_ID."
  value       = module.network.security_group_ids.migration
}

output "app_base_url" {
  description = "GitHub environment variable APP_BASE_URL (hostname only, no scheme)."
  value       = module.edge.primary_domain_name
}
