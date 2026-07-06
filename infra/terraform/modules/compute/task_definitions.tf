locals {
  task_container_defaults = {
    readonly_root_filesystem = true
    user                     = "10001:10001"
    essential                = true
    linux_parameters = {
      init_process_enabled = true
    }
    mount_points = [
      {
        sourceVolume  = "tmp"
        containerPath = "/tmp"
        readOnly      = false
      },
    ]
    log_configuration = {
      logDriver = "awslogs"
    }
  }

  common_api_secrets = [
    {
      name      = "VYU_DATABASE_URL"
      valueFrom = var.secret_arns["database_connection"]
    },
    {
      name      = "VYU_PROVIDERS_CONFIG_SECRET_ARN"
      valueFrom = var.secret_arns["providers"]
    },
  ]
}

resource "aws_ecs_task_definition" "web" {
  family                   = "vyu-${var.environment}-web"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu.web
  memory                   = var.task_memory.web
  execution_role_arn       = aws_iam_role.execution["web"].arn
  task_role_arn            = aws_iam_role.task["web"].arn
  track_latest             = false

  ephemeral_storage {
    size_in_gib = var.ephemeral_storage_gib
  }

  volume {
    name = "tmp"
  }

  container_definitions = jsonencode([
    {
      name                   = "web"
      image                  = "${local.image_repositories.web}@${var.image_digests.web}"
      essential              = true
      user                   = local.task_container_defaults.user
      readonlyRootFilesystem = local.task_container_defaults.readonly_root_filesystem
      portMappings = [
        {
          containerPort = var.web_container_port
          protocol      = "tcp"
        },
      ]
      environment = [
        { name = "NODE_ENV", value = "production" },
        { name = "NEXT_PUBLIC_APP_ENV", value = var.environment == "prod" ? "production" : var.environment },
        { name = "NEXT_PUBLIC_USE_FIXTURES", value = "false" },
        { name = "PORT", value = tostring(var.web_container_port) },
        { name = "HOSTNAME", value = "0.0.0.0" },
      ]
      mountPoints     = local.task_container_defaults.mount_points
      linuxParameters = local.task_container_defaults.linux_parameters
      healthCheck = {
        command     = ["CMD-SHELL", "curl -fsS http://127.0.0.1:${var.web_container_port}/api/health || exit 1"]
        interval    = 10
        timeout     = 3
        retries     = 3
        startPeriod = 30
      }
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.service["web"].name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "web"
        }
      }
    },
  ])

  tags = merge(local.common_task_tags, { Workload = "web" })
}

resource "aws_ecs_task_definition" "api" {
  family                   = "vyu-${var.environment}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu.api
  memory                   = var.task_memory.api
  execution_role_arn       = aws_iam_role.execution["api"].arn
  task_role_arn            = aws_iam_role.task["api"].arn
  track_latest             = false

  ephemeral_storage {
    size_in_gib = var.ephemeral_storage_gib
  }

  volume {
    name = "tmp"
  }

  container_definitions = jsonencode([
    {
      name                   = "api"
      image                  = "${local.image_repositories.api}@${var.image_digests.api}"
      essential              = true
      user                   = local.task_container_defaults.user
      readonlyRootFilesystem = local.task_container_defaults.readonly_root_filesystem
      portMappings = [
        {
          containerPort = var.api_container_port
          protocol      = "tcp"
        },
      ]
      environment = [
        { name = "VYU_ENV", value = var.environment },
        { name = "VYU_EVIDENCE_BUCKET", value = var.bucket_names.evidence },
        { name = "VYU_EXPORTS_BUCKET", value = var.bucket_names.exports },
        { name = "VYU_SQS_INGESTION_QUEUE_URL", value = var.queue_urls["ingestion"] },
        { name = "VYU_SQS_RESEARCH_QUEUE_URL", value = var.queue_urls["research"] },
        { name = "VYU_SQS_SYNTHESIS_QUEUE_URL", value = var.queue_urls["synthesis"] },
        { name = "VYU_SQS_EXPORT_QUEUE_URL", value = var.queue_urls["export"] },
      ]
      secrets         = local.common_api_secrets
      mountPoints     = local.task_container_defaults.mount_points
      linuxParameters = local.task_container_defaults.linux_parameters
      healthCheck = {
        command     = ["CMD-SHELL", "curl -fsS http://127.0.0.1:${var.api_container_port}/v1/health/live || exit 1"]
        interval    = 10
        timeout     = 3
        retries     = 3
        startPeriod = 20
      }
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.service["api"].name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "api"
        }
      }
    },
  ])

  tags = merge(local.common_task_tags, { Workload = "api" })
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "vyu-${var.environment}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu.worker
  memory                   = var.task_memory.worker
  execution_role_arn       = aws_iam_role.execution["worker"].arn
  task_role_arn            = aws_iam_role.task["worker"].arn
  track_latest             = false

  ephemeral_storage {
    size_in_gib = var.ephemeral_storage_gib
  }

  volume {
    name = "tmp"
  }

  container_definitions = jsonencode([
    {
      name                   = "worker"
      image                  = "${local.image_repositories.worker}@${var.image_digests.worker}"
      essential              = true
      user                   = local.task_container_defaults.user
      readonlyRootFilesystem = local.task_container_defaults.readonly_root_filesystem
      environment = [
        { name = "VYU_ENV", value = var.environment },
        { name = "VYU_SQS_QUEUE_URL", value = var.queue_urls["ingestion"] },
        { name = "VYU_EVIDENCE_BUCKET", value = var.bucket_names.evidence },
        { name = "VYU_EXPORTS_BUCKET", value = var.bucket_names.exports },
      ]
      secrets         = local.common_api_secrets
      mountPoints     = local.task_container_defaults.mount_points
      linuxParameters = local.task_container_defaults.linux_parameters
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.service["worker"].name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "worker"
        }
      }
    },
  ])

  tags = merge(local.common_task_tags, { Workload = "worker" })
}

resource "aws_ecs_task_definition" "migration" {
  family                   = "vyu-${var.environment}-migration"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu.migration
  memory                   = var.task_memory.migration
  execution_role_arn       = aws_iam_role.execution["migration"].arn
  task_role_arn            = aws_iam_role.task["migration"].arn
  track_latest             = false

  ephemeral_storage {
    size_in_gib = var.ephemeral_storage_gib
  }

  volume {
    name = "tmp"
  }

  container_definitions = jsonencode([
    {
      name                   = "migration"
      image                  = "${local.image_repositories.migration}@${var.image_digests.api}"
      essential              = true
      user                   = local.task_container_defaults.user
      readonlyRootFilesystem = local.task_container_defaults.readonly_root_filesystem
      command                = ["uv", "run", "alembic", "upgrade", "head"]
      environment = [
        { name = "VYU_ENV", value = var.environment },
      ]
      secrets = [
        {
          name      = "VYU_DATABASE_URL"
          valueFrom = var.secret_arns["database_connection"]
        },
      ]
      mountPoints     = local.task_container_defaults.mount_points
      linuxParameters = local.task_container_defaults.linux_parameters
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.service["migration"].name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "migration"
        }
      }
    },
  ])

  tags = merge(local.common_task_tags, { Workload = "migration" })
}
