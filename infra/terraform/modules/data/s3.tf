resource "aws_s3_bucket" "access_logs" {
  bucket = local.bucket_names.access_logs

  tags = {
    Name        = local.bucket_names.access_logs
    Environment = var.environment
    Purpose     = "access-logs"
  }
}

resource "aws_s3_bucket_ownership_controls" "access_logs" {
  bucket = aws_s3_bucket.access_logs.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "access_logs" {
  bucket = aws_s3_bucket.access_logs.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "access_logs" {
  bucket = aws_s3_bucket.access_logs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.data_kms_key_arn
    }
  }
}

resource "aws_s3_bucket_versioning" "access_logs" {
  bucket = aws_s3_bucket.access_logs.id

  versioning_configuration {
    status = "Enabled"
  }
}

locals {
  application_buckets = {
    evidence = {
      kms_key_arn = var.data_kms_key_arn
      object_lock = false
    }
    exports = {
      kms_key_arn = var.data_kms_key_arn
      object_lock = false
    }
    audit = {
      kms_key_arn = var.audit_kms_key_arn
      object_lock = true
    }
  }
}

resource "aws_s3_bucket" "application" {
  for_each = local.application_buckets

  bucket = local.bucket_names[each.key]

  object_lock_enabled = each.value.object_lock

  tags = {
    Name        = local.bucket_names[each.key]
    Environment = var.environment
    Purpose     = each.key
  }
}

resource "aws_s3_bucket_ownership_controls" "application" {
  for_each = aws_s3_bucket.application

  bucket = each.value.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "application" {
  for_each = aws_s3_bucket.application

  bucket = each.value.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "application" {
  for_each = aws_s3_bucket.application

  bucket = each.value.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "application" {
  for_each = aws_s3_bucket.application

  bucket = each.value.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = local.application_buckets[each.key].kms_key_arn
    }
  }
}

resource "aws_s3_bucket_logging" "application" {
  for_each = aws_s3_bucket.application

  bucket = each.value.id

  target_bucket = aws_s3_bucket.access_logs.id
  target_prefix = "${each.key}/"
}

resource "aws_s3_bucket_lifecycle_configuration" "application" {
  for_each = aws_s3_bucket.application

  bucket = each.value.id

  rule {
    id     = "expire-noncurrent"
    status = "Enabled"

    noncurrent_version_expiration {
      noncurrent_days = local.is_production ? 90 : 30
    }
  }
}

resource "aws_s3_bucket_object_lock_configuration" "audit" {
  bucket = aws_s3_bucket.application["audit"].id

  rule {
    default_retention {
      mode = local.is_production ? "COMPLIANCE" : "GOVERNANCE"
      days = local.is_production ? 365 : 30
    }
  }
}

data "aws_iam_policy_document" "tls_only" {
  for_each = aws_s3_bucket.application

  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    actions   = ["s3:*"]
    resources = [each.value.arn, "${each.value.arn}/*"]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "application" {
  for_each = { for key, bucket in aws_s3_bucket.application : key => bucket if key != "evidence" }

  bucket = each.value.id
  policy = data.aws_iam_policy_document.tls_only[each.key].json
}
