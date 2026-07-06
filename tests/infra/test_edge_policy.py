from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EDGE_MODULE = ROOT / "infra" / "terraform" / "modules" / "edge"
NETWORK_MODULE = ROOT / "infra" / "terraform" / "modules" / "network"
DATA_MODULE = ROOT / "infra" / "terraform" / "modules" / "data"

MANAGED_WAF_RULES = (
    "AWSManagedRulesCommonRuleSet",
    "AWSManagedRulesKnownBadInputsRuleSet",
    "AWSManagedRulesAmazonIpReputationList",
    "AWSManagedRulesSQLiRuleSet",
)


def _read_module_tf(module_dir: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(module_dir.glob("*.tf")))


def test_acm_uses_route53_dns_validation() -> None:
    content = _read_module_tf(EDGE_MODULE)
    assert 'resource "aws_acm_certificate" "regional"' in content
    assert 'resource "aws_acm_certificate" "cloudfront"' in content
    assert 'resource "aws_route53_record" "regional_cert_validation"' in content
    assert 'resource "aws_acm_certificate_validation" "regional"' in content


def test_cloudfront_redirects_to_https_and_sets_tls_version() -> None:
    content = (EDGE_MODULE / "cloudfront.tf").read_text(encoding="utf-8")
    assert "viewer_protocol_policy = \"redirect-to-https\"" in content
    assert 'minimum_protocol_version = "TLSv1.2_2021"' in content


def test_cloudfront_disables_api_caching() -> None:
    content = (EDGE_MODULE / "cloudfront.tf").read_text(encoding="utf-8")
    assert 'path_pattern           = "/v1/*"' in content
    assert "4135ea2d-6df8-44a3-9df3-4b5a84be39ad" in content


def test_cloudfront_uses_oac_for_s3_origin_and_redacts_cookies_in_logs() -> None:
    content = _read_module_tf(EDGE_MODULE)
    assert 'resource "aws_cloudfront_origin_access_control" "evidence"' in content
    assert "origin_access_control_id" in content
    assert "include_cookies = false" in content


def test_response_headers_policy_sets_security_headers() -> None:
    content = (EDGE_MODULE / "response_headers.tf").read_text(encoding="utf-8")
    assert "strict_transport_security" in content
    assert "content_security_policy" in content
    assert "frame_options" in content
    assert "referrer_policy" in content
    assert "Permissions-Policy" in content


def test_waf_enables_managed_rules_rate_limits_and_body_size_limits() -> None:
    content = (EDGE_MODULE / "waf.tf").read_text(encoding="utf-8")
    assert 'scope = "CLOUDFRONT"' in content
    assert "rate_based_statement" in content
    assert "size_constraint_statement" in content
    for rule in MANAGED_WAF_RULES:
        assert rule in content


def test_waf_is_associated_with_cloudfront() -> None:
    content = (EDGE_MODULE / "cloudfront.tf").read_text(encoding="utf-8")
    assert "web_acl_id          = aws_wafv2_web_acl.cloudfront.arn" in content


def test_alb_ingress_remains_cloudfront_restricted() -> None:
    security_groups = (NETWORK_MODULE / "security_groups.tf").read_text(encoding="utf-8")
    assert "prefix_list_id = data.aws_ec2_managed_prefix_list.cloudfront_origin_facing.id" in security_groups


def test_evidence_bucket_policy_denies_public_and_allows_oac_only() -> None:
    content = (EDGE_MODULE / "s3_oac.tf").read_text(encoding="utf-8")
    assert "DenyInsecureTransport" in content
    assert "cloudfront.amazonaws.com" in content
    data_s3 = (DATA_MODULE / "s3.tf").read_text(encoding="utf-8")
    assert 'if key != "evidence"' in data_s3


def test_terraform_validate_dev_environment() -> None:
    init = subprocess.run(
        ["terraform", "-chdir=infra/terraform/environments/dev", "init", "-backend=false"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert init.returncode == 0, init.stderr

    validate = subprocess.run(
        ["terraform", "-chdir=infra/terraform/environments/dev", "validate"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert validate.returncode == 0, validate.stderr
