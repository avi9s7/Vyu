data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.region

  key_definitions = {
    data = {
      description = "VYU ${var.environment} application data encryption"
      alias       = "alias/vyu-${var.environment}-data"
    }
    audit_archive = {
      description = "VYU ${var.environment} audit archive encryption"
      alias       = "alias/vyu-${var.environment}-audit-archive"
    }
    secrets = {
      description = "VYU ${var.environment} secrets encryption"
      alias       = "alias/vyu-${var.environment}-secrets"
    }
    logs = {
      description = "VYU ${var.environment} log encryption"
      alias       = "alias/vyu-${var.environment}-logs"
    }
    state = {
      description = "VYU ${var.environment} terraform state encryption"
      alias       = "alias/vyu-${var.environment}-state"
    }
  }
}

resource "aws_kms_key" "this" {
  for_each = local.key_definitions

  description             = each.value.description
  enable_key_rotation     = true
  deletion_window_in_days = var.environment == "prod" ? 30 : 7

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EnableAccountRootAdministration"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${local.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "AllowCloudWatchLogsUse"
        Effect = "Allow"
        Principal = {
          Service = "logs.${local.region}.amazonaws.com"
        }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:CreateGrant",
          "kms:DescribeKey",
        ]
        Resource = "*"
        Condition = {
          ArnLike = {
            "kms:EncryptionContext:aws:logs:arn" = "arn:aws:logs:${local.region}:${local.account_id}:*"
          }
        }
      },
    ]
  })

  tags = {
    Name        = each.key
    Environment = var.environment
    Purpose     = each.key
  }
}

resource "aws_kms_alias" "this" {
  for_each = local.key_definitions

  name          = each.value.alias
  target_key_id = aws_kms_key.this[each.key].key_id
}
