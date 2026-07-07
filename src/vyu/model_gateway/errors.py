from __future__ import annotations


class GatewayError(Exception):
    """Base model gateway error with a safe client-facing code."""

    safe_code: str = "gateway_error"

    def __init__(self, message: str, *, safe_code: str | None = None) -> None:
        super().__init__(message)
        if safe_code is not None:
            self.safe_code = safe_code


class GatewayValidationError(GatewayError):
    safe_code = "gateway_validation_error"


class GatewayPolicyBlocked(GatewayError):
    safe_code = "gateway_policy_blocked"


class GatewayRateLimited(GatewayError):
    safe_code = "gateway_rate_limited"

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class GatewayTimeout(GatewayError):
    safe_code = "gateway_timeout"


class GatewayUnavailable(GatewayError):
    safe_code = "gateway_unavailable"


class GatewayMalformedResponse(GatewayError):
    safe_code = "gateway_malformed_response"


class GatewayAuthenticationError(GatewayError):
    safe_code = "gateway_authentication_error"
