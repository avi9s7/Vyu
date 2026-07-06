output "oidc_provider_arn" {
  value = local.github_oidc_provider_arn
}

output "plan_role_arn" {
  value = aws_iam_role.plan.arn
}

output "apply_role_arn" {
  value = aws_iam_role.apply.arn
}

output "build_role_arn" {
  value = aws_iam_role.build.arn
}
