resource "aws_secretsmanager_secret" "this" {
  for_each = local.secret_names

  name                    = each.value
  description             = "VYU ${var.environment} ${replace(each.key, "_", " ")} secret container"
  kms_key_id              = var.secrets_kms_key_arn
  recovery_window_in_days = local.is_production ? 30 : 0

  tags = {
    Name        = each.value
    Environment = var.environment
    Purpose     = each.key
  }
}
