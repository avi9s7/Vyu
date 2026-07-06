resource "aws_ecr_repository" "this" {
  for_each = local.ecr_repositories

  name                 = each.value
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = var.data_kms_key_arn
  }

  tags = {
    Name        = each.value
    Environment = var.environment
    Workload    = each.key
  }
}

resource "aws_ecr_lifecycle_policy" "this" {
  for_each = aws_ecr_repository.this

  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Retain the most recent release images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = local.is_production ? 50 : 20
        }
        action = {
          type = "expire"
        }
      },
    ]
  })
}

data "aws_iam_policy_document" "ecr_repository" {
  for_each = aws_ecr_repository.this

  statement {
    sid    = "AllowPushFromCiAndDeployRoles"
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = length(var.ecr_push_role_arns) > 0 ? var.ecr_push_role_arns : ["arn:aws:iam::${local.account_id}:root"]
    }
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:CompleteLayerUpload",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
  }

  statement {
    sid    = "AllowPullFromRuntimeRoles"
    effect = "Allow"
    principals {
      type = "AWS"
      identifiers = distinct(concat(
        var.ecr_pull_role_arns,
        [for role in aws_iam_role.execution : role.arn],
      ))
    }
    actions = [
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
  }
}

resource "aws_ecr_repository_policy" "this" {
  for_each = aws_ecr_repository.this

  repository = each.value.name
  policy     = data.aws_iam_policy_document.ecr_repository[each.key].json
}
