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
