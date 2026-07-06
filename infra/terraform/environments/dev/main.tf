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

  environment                = var.environment
  aws_region                 = var.aws_region
  vpc_id                     = module.network.vpc_id
  database_subnet_ids        = module.network.database_subnet_ids
  database_security_group_id = module.network.security_group_ids.database
  data_kms_key_arn           = module.kms.data_key_arn
  audit_kms_key_arn          = module.kms.audit_archive_key_arn
  secrets_kms_key_arn        = module.kms.secrets_key_arn
}

module "queues" {
  source = "../../modules/queues"

  environment = var.environment
  aws_region  = var.aws_region
  kms_key_arn = module.kms.data_key_arn
}

module "identity" {
  source = "../../modules/identity"

  environment                = var.environment
  aws_region                 = var.aws_region
  callback_urls              = var.identity_callback_urls
  logout_urls                = var.identity_logout_urls
  cognito_domain_prefix      = var.identity_cognito_domain_prefix
  resource_server_identifier = var.identity_resource_server_identifier
  saml_identity_providers    = var.identity_saml_identity_providers
  oidc_identity_providers    = var.identity_oidc_identity_providers
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
}

module "edge" {
  source = "../../modules/edge"

  providers = {
    aws.us_east_1 = aws.us_east_1
  }

  environment                    = var.environment
  aws_region                     = var.aws_region
  primary_domain_name            = var.edge_primary_domain_name
  route53_zone_id                = var.edge_route53_zone_id
  alb_arn                        = module.compute.alb_arn
  alb_dns_name                   = module.compute.alb_dns_name
  target_group_arns              = module.compute.target_group_arns
  evidence_bucket_name           = module.data.bucket_names["evidence"]
  access_logs_bucket_domain_name = module.data.access_logs_bucket_domain_name
}

module "observability" {
  source = "../../modules/observability"

  environment                       = var.environment
  aws_region                        = var.aws_region
  logs_kms_key_arn                  = module.kms.logs_key_arn
  alb_arn_suffix                    = module.compute.alb_arn_suffix
  ecs_cluster_name                  = module.compute.cluster_name
  ecs_service_names                 = module.compute.service_names
  database_instance_identifier      = module.data.database_instance_identifier
  cognito_user_pool_id              = module.identity.user_pool_id
  waf_web_acl_name                  = module.edge.waf_web_acl_name
  service_log_group_names           = module.compute.log_group_names
  queue_names                       = module.queues.queue_names
  dlq_names                         = module.queues.dlq_names
  on_call_email_addresses           = var.observability_on_call_email_addresses
  critical_alarm_owner_acknowledged = var.observability_critical_alarm_owner_acknowledged
}

module "github_oidc" {
  source      = "../../modules/github_oidc"
  environment = var.environment
  aws_region  = var.aws_region
}
