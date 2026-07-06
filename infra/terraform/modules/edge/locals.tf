locals {
  is_production = var.environment == "prod"
  name_prefix   = "vyu-${var.environment}"

  api_path_prefixes = ["/v1/*", "/docs*", "/openapi.json"]
  upload_path_prefixes = ["/v1/uploads/*", "/v1/evidence/*"]

  security_headers = {
    strict_transport_security = "max-age=63072000; includeSubDomains; preload"
    content_type_options      = { override = true }
    frame_options             = { frame_option = "DENY", override = true }
    referrer_policy           = { referrer_policy = "strict-origin-when-cross-origin", override = true }
    content_security_policy   = "default-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self';"
    permissions_policy      = "camera=(), microphone=(), geolocation=(), payment=()"
  }
}
