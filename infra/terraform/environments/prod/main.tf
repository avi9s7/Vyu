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
  source = "../../modules/data"

  environment                 = var.environment
  aws_region                  = var.aws_region
  vpc_id                      = module.network.vpc_id
  database_subnet_ids         = module.network.database_subnet_ids
  database_security_group_id  = module.network.security_group_ids.database
  data_kms_key_arn            = module.kms.data_key_arn
  audit_kms_key_arn           = module.kms.audit_archive_key_arn
  secrets_kms_key_arn         = module.kms.secrets_key_arn
}

module "queues" {
  source = "../../modules/queues"

  environment  = var.environment
  aws_region   = var.aws_region
  kms_key_arn  = module.kms.data_key_arn
}

module "identity" {
  source = "../../modules/identity"

  environment                  = var.environment
  aws_region                   = var.aws_region
  callback_urls                = var.identity_callback_urls
  logout_urls                  = var.identity_logout_urls
  cognito_domain_prefix        = var.identity_cognito_domain_prefix
  resource_server_identifier   = var.identity_resource_server_identifier
  saml_identity_providers      = var.identity_saml_identity_providers
  oidc_identity_providers      = var.identity_oidc_identity_providers
}

module "edge" {
  source      = "../../modules/edge"
  environment = var.environment
  aws_region  = var.aws_region
}

module "compute" {
  source = "../../modules/compute"

  environment                     = var.environment
  aws_region                      = var.aws_region
  vpc_id                          = module.network.vpc_id
  public_subnet_ids               = module.network.public_subnet_ids
  private_subnet_ids              = module.network.private_subnet_ids
  security_group_ids              = module.network.security_group_ids
  logs_kms_key_arn                = module.kms.logs_key_arn
  data_kms_key_arn                = module.kms.data_key_arn
  secrets_kms_key_arn             = module.kms.secrets_key_arn
  database_master_user_secret_arn = module.data.database_master_user_secret_arn
  secret_arns                     = module.data.secret_arns
  bucket_names                    = module.data.bucket_names
  queue_arns                      = module.queues.queue_arns
  queue_urls                      = module.queues.queue_urls
  image_digests                   = var.compute_image_digests
  ecr_push_role_arns              = var.compute_ecr_push_role_arns
  alb_certificate_arn             = var.compute_alb_certificate_arn
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
