data "aws_iam_policy_document" "plan_trust" {
  statement {
    effect = "Allow"

    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_provider_arn]
    }

    actions = ["sts:AssumeRoleWithWebIdentity"]

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = [var.github_oidc_audience]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:${var.github_repository}:pull_request",
        "repo:${var.github_repository}:ref:refs/heads/main",
        "repo:${var.github_repository}:ref:refs/heads/cursor/*",
      ]
    }
  }
}

data "aws_iam_policy_document" "apply_trust" {
  statement {
    effect = "Allow"

    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_provider_arn]
    }

    actions = ["sts:AssumeRoleWithWebIdentity"]

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = [var.github_oidc_audience]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:environment:${var.environment}"]
    }
  }
}

data "aws_iam_policy_document" "build_trust" {
  statement {
    effect = "Allow"

    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_provider_arn]
    }

    actions = ["sts:AssumeRoleWithWebIdentity"]

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = [var.github_oidc_audience]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:${var.github_repository}:ref:refs/heads/main",
        "repo:${var.github_repository}:environment:${var.environment}",
      ]
    }
  }
}

resource "aws_iam_role" "plan" {
  name               = "${local.name_prefix}-github-plan"
  assume_role_policy = data.aws_iam_policy_document.plan_trust.json

  tags = {
    Name        = "${local.name_prefix}-github-plan"
    Environment = var.environment
    Purpose     = "terraform-plan"
  }
}

resource "aws_iam_role" "apply" {
  name               = "${local.name_prefix}-github-apply"
  assume_role_policy = data.aws_iam_policy_document.apply_trust.json

  tags = {
    Name        = "${local.name_prefix}-github-apply"
    Environment = var.environment
    Purpose     = "terraform-apply"
  }
}

resource "aws_iam_role" "build" {
  name               = "${local.name_prefix}-github-build"
  assume_role_policy = data.aws_iam_policy_document.build_trust.json

  tags = {
    Name        = "${local.name_prefix}-github-build"
    Environment = var.environment
    Purpose     = "container-build"
  }
}
