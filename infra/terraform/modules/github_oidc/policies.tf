data "aws_iam_policy_document" "plan" {
  statement {
    sid    = "ReadTerraformState"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:ListBucket",
    ]
    resources = [
      local.state_bucket_arn,
      "${local.state_bucket_arn}/*",
    ]
  }

  dynamic "statement" {
    for_each = var.terraform_state_lock_table_arn != "" ? [var.terraform_state_lock_table_arn] : []
    content {
      sid    = "UseTerraformStateLock"
      effect = "Allow"
      actions = [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:DeleteItem",
        "dynamodb:DescribeTable",
      ]
      resources = [statement.value]
    }
  }

  statement {
    sid    = "TerraformPlanReadOnly"
    effect = "Allow"
    actions = [
      "ec2:Describe*",
      "ecs:Describe*",
      "elasticloadbalancing:Describe*",
      "rds:Describe*",
      "sqs:GetQueueAttributes",
      "sqs:ListQueues",
      "s3:GetBucket*",
      "s3:ListBucket",
      "s3:GetObject",
      "iam:Get*",
      "iam:List*",
      "kms:Describe*",
      "kms:List*",
      "logs:Describe*",
      "cloudwatch:Describe*",
      "cognito-idp:Describe*",
      "cognito-idp:List*",
      "wafv2:Get*",
      "wafv2:List*",
      "acm:Describe*",
      "acm:List*",
      "route53:List*",
      "route53:Get*",
      "sns:Get*",
      "sns:List*",
      "ssm:GetParameter",
      "ssm:GetParameters",
    ]
    resources = ["*"]
  }
}

data "aws_iam_policy_document" "apply" {
  statement {
    sid    = "ManageTerraformState"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
    ]
    resources = [
      local.state_bucket_arn,
      "${local.state_bucket_arn}/*",
    ]
  }

  dynamic "statement" {
    for_each = var.terraform_state_lock_table_arn != "" ? [var.terraform_state_lock_table_arn] : []
    content {
      sid    = "UseTerraformStateLock"
      effect = "Allow"
      actions = [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:DeleteItem",
        "dynamodb:DescribeTable",
      ]
      resources = [statement.value]
    }
  }

  statement {
    sid    = "DeployApplicationInfrastructure"
    effect = "Allow"
    actions = [
      "ecs:UpdateService",
      "ecs:DescribeServices",
      "ecs:DescribeTaskDefinition",
      "ecs:RegisterTaskDefinition",
      "ecs:RunTask",
      "ecs:DescribeTasks",
      "ecs:ListTasks",
      "iam:PassRole",
    ]
    resources = concat(
      [local.ecs_cluster_arn],
      local.ecs_service_arns,
      [local.migration_task_definition_arn],
    )
  }
}

data "aws_iam_policy_document" "build" {
  statement {
    sid    = "PushImmutableImages"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:CompleteLayerUpload",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
      "ecr:GetAuthorizationToken",
    ]
    resources = local.ecr_repository_arns
  }

  statement {
    sid       = "AuthorizeEcr"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "plan" {
  name   = "${local.name_prefix}-github-plan"
  role   = aws_iam_role.plan.id
  policy = data.aws_iam_policy_document.plan.json
}

resource "aws_iam_role_policy" "apply" {
  name   = "${local.name_prefix}-github-apply"
  role   = aws_iam_role.apply.id
  policy = data.aws_iam_policy_document.apply.json
}

resource "aws_iam_role_policy" "build" {
  name   = "${local.name_prefix}-github-build"
  role   = aws_iam_role.build.id
  policy = data.aws_iam_policy_document.build.json
}
