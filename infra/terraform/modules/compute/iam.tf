resource "aws_iam_role" "execution" {
  for_each = toset(["web", "api", "worker", "migration"])

  name = "vyu-${var.environment}-${each.key}-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      },
    ]
  })

  tags = {
    Environment = var.environment
    Workload    = each.key
    RoleType    = "execution"
  }
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  for_each = aws_iam_role.execution

  role       = each.value.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_secrets" {
  statement {
    sid    = "ReadReferencedSecrets"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
    ]
    resources = distinct(concat(
      [var.database_master_user_secret_arn],
      values(var.secret_arns),
    ))
  }

  statement {
    sid    = "DecryptSecretsKms"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:DescribeKey",
    ]
    resources = [var.secrets_kms_key_arn]
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  for_each = aws_iam_role.execution

  name   = "vyu-${var.environment}-${each.key}-execution-secrets"
  role   = each.value.id
  policy = data.aws_iam_policy_document.execution_secrets.json
}

resource "aws_iam_role" "task" {
  for_each = toset(["web", "api", "worker", "migration"])

  name = "vyu-${var.environment}-${each.key}-task"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      },
    ]
  })

  tags = {
    Environment = var.environment
    Workload    = each.key
    RoleType    = "task"
  }
}

data "aws_iam_policy_document" "task_web" {
  statement {
    sid    = "WriteServiceLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.service["web"].arn}:*"]
  }
}

data "aws_iam_policy_document" "task_api" {
  statement {
    sid    = "WriteServiceLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.service["api"].arn}:*"]
  }

  statement {
    sid    = "ReadDatabaseSecret"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
    ]
    resources = distinct(concat(
      [var.database_master_user_secret_arn, var.secret_arns["database_connection"], var.secret_arns["providers"]],
    ))
  }

  statement {
    sid    = "UseApplicationBuckets"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
      "s3:GetObjectVersion",
    ]
    resources = [
      "arn:aws:s3:::${var.bucket_names.evidence}",
      "arn:aws:s3:::${var.bucket_names.evidence}/*",
      "arn:aws:s3:::${var.bucket_names.exports}",
      "arn:aws:s3:::${var.bucket_names.exports}/*",
    ]
  }

  statement {
    sid    = "PublishJobs"
    effect = "Allow"
    actions = [
      "sqs:SendMessage",
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl",
    ]
    resources = values(var.queue_arns)
  }

  statement {
    sid    = "DecryptDataKeys"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:GenerateDataKey",
      "kms:DescribeKey",
    ]
    resources = [var.data_kms_key_arn, var.secrets_kms_key_arn]
  }
}

data "aws_iam_policy_document" "task_worker" {
  statement {
    sid    = "WriteServiceLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.service["worker"].arn}:*"]
  }

  statement {
    sid    = "ReadRuntimeSecrets"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
    ]
    resources = distinct(concat(
      [var.database_master_user_secret_arn, var.secret_arns["database_connection"], var.secret_arns["providers"]],
    ))
  }

  statement {
    sid    = "UseEvidenceAndExportBuckets"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
      "s3:GetObjectVersion",
    ]
    resources = [
      "arn:aws:s3:::${var.bucket_names.evidence}",
      "arn:aws:s3:::${var.bucket_names.evidence}/*",
      "arn:aws:s3:::${var.bucket_names.exports}",
      "arn:aws:s3:::${var.bucket_names.exports}/*",
    ]
  }

  statement {
    sid    = "ConsumeWorkloadQueues"
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:ChangeMessageVisibility",
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl",
    ]
    resources = values(var.queue_arns)
  }

  statement {
    sid    = "DecryptDataKeys"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:GenerateDataKey",
      "kms:DescribeKey",
    ]
    resources = [var.data_kms_key_arn, var.secrets_kms_key_arn]
  }
}

data "aws_iam_policy_document" "task_migration" {
  statement {
    sid    = "WriteServiceLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.service["migration"].arn}:*"]
  }

  statement {
    sid    = "ReadDatabaseSecret"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
    ]
    resources = distinct(concat(
      [var.database_master_user_secret_arn, var.secret_arns["database_connection"]],
    ))
  }

  statement {
    sid    = "DecryptSecretsKms"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:DescribeKey",
    ]
    resources = [var.secrets_kms_key_arn]
  }
}

resource "aws_iam_role_policy" "task_web" {
  name   = "vyu-${var.environment}-web-task"
  role   = aws_iam_role.task["web"].id
  policy = data.aws_iam_policy_document.task_web.json
}

resource "aws_iam_role_policy" "task_api" {
  name   = "vyu-${var.environment}-api-task"
  role   = aws_iam_role.task["api"].id
  policy = data.aws_iam_policy_document.task_api.json
}

resource "aws_iam_role_policy" "task_worker" {
  name   = "vyu-${var.environment}-worker-task"
  role   = aws_iam_role.task["worker"].id
  policy = data.aws_iam_policy_document.task_worker.json
}

resource "aws_iam_role_policy" "task_migration" {
  name   = "vyu-${var.environment}-migration-task"
  role   = aws_iam_role.task["migration"].id
  policy = data.aws_iam_policy_document.task_migration.json
}
