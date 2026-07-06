output "database_endpoint" {
  value = aws_db_instance.postgres.address
}

output "database_port" {
  value = aws_db_instance.postgres.port
}

output "database_master_user_secret_arn" {
  value = aws_db_instance.postgres.master_user_secret[0].secret_arn
}

output "bucket_names" {
  value = { for key, bucket in aws_s3_bucket.application : key => bucket.bucket }
}

output "access_logs_bucket_domain_name" {
  value = aws_s3_bucket.access_logs.bucket_regional_domain_name
}

output "secret_arns" {
  value = { for key, secret in aws_secretsmanager_secret.this : key => secret.arn }
}
