output "key_arns" {
  description = "Customer-managed KMS key ARNs keyed by purpose."
  value       = { for name, key in aws_kms_key.this : name => key.arn }
}

output "data_key_arn" {
  value = aws_kms_key.this["data"].arn
}

output "audit_archive_key_arn" {
  value = aws_kms_key.this["audit_archive"].arn
}

output "secrets_key_arn" {
  value = aws_kms_key.this["secrets"].arn
}

output "logs_key_arn" {
  value = aws_kms_key.this["logs"].arn
}

output "state_key_arn" {
  value = aws_kms_key.this["state"].arn
}
