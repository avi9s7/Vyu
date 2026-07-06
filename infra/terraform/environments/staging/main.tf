module "network" {
  source             = "../../modules/network"
  environment        = var.environment
  aws_region         = var.aws_region
  single_nat_gateway = var.single_nat_gateway
}

module "kms" {
  source      = "../../modules/kms"
  environment = var.environment
  aws_region  = var.aws_region
}

module "data" {
  source      = "../../modules/data"
  environment = var.environment
  aws_region  = var.aws_region
}

module "queues" {
  source      = "../../modules/queues"
  environment = var.environment
  aws_region  = var.aws_region
}

module "identity" {
  source      = "../../modules/identity"
  environment = var.environment
  aws_region  = var.aws_region
}

module "edge" {
  source      = "../../modules/edge"
  environment = var.environment
  aws_region  = var.aws_region
}

module "compute" {
  source      = "../../modules/compute"
  environment = var.environment
  aws_region  = var.aws_region
}

module "observability" {
  source      = "../../modules/observability"
  environment = var.environment
  aws_region  = var.aws_region
}

module "github_oidc" {
  source      = "../../modules/github_oidc"
  environment = var.environment
  aws_region  = var.aws_region
}
