output "aws_region" {
  value = var.aws_region
}

output "aws_account_id" {
  value = data.aws_caller_identity.current.account_id
}

output "state_bucket_name" {
  value = aws_s3_bucket.terraform_state.bucket
}

output "state_bucket_arn" {
  value = aws_s3_bucket.terraform_state.arn
}

output "lock_table_name" {
  value = aws_dynamodb_table.terraform_lock.name
}

output "lock_table_arn" {
  value = aws_dynamodb_table.terraform_lock.arn
}

output "state_kms_key_arn" {
  value = aws_kms_key.terraform_state.arn
}

output "state_kms_key_id" {
  value = aws_kms_key.terraform_state.key_id
}

output "backend_hcl_snippet" {
  description = "Paste into environments/<env>/backend.hcl (adjust key per environment)."
  value       = <<-EOT
    bucket         = "${aws_s3_bucket.terraform_state.bucket}"
    region         = "${var.aws_region}"
    encrypt        = true
    kms_key_id     = "${aws_kms_key.terraform_state.arn}"
    dynamodb_table = "${aws_dynamodb_table.terraform_lock.name}"
  EOT
}
