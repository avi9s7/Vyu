output "regional_certificate_arn" {
  value = aws_acm_certificate_validation.regional.certificate_arn
}

output "cloudfront_certificate_arn" {
  value = aws_acm_certificate_validation.cloudfront.certificate_arn
}

output "cloudfront_distribution_id" {
  value = aws_cloudfront_distribution.this.id
}

output "cloudfront_domain_name" {
  value = aws_cloudfront_distribution.this.domain_name
}

output "primary_domain_name" {
  value = var.primary_domain_name
}

output "waf_web_acl_arn" {
  value = aws_wafv2_web_acl.cloudfront.arn
}
