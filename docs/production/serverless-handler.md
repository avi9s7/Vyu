# Serverless Handler

The serverless handler is the first callable deployment packaging boundary for API Gateway-style HTTP events.

The implementation is `src/vyu/deployment/serverless_handler.py`. It wraps `DeploymentApiServiceShell`, accepts serverless HTTP events, returns API Gateway-compatible response dictionaries, and keeps authentication, identity mapping, service routing, and domain behavior in the existing deployment and entrypoint modules.

## Serverless Handler Contract

The module provides:

- `ServerlessDeploymentHandler`
- `ServerlessHandlerConfig`
- `serverless_handler_from_deployment_handler`

Malformed framework/serverless events are converted into stable JSON error responses instead of escaping as runtime exceptions. Error reasons include `serverless_request_invalid` and `serverless_handler_error`.

## Current Limits

- No cloud deployment package or infrastructure template is created here.
- IAM, API Gateway routes, CORS, WAF, rate limits, and secrets remain outside this module.
- The caller still injects the deployment handler or composed runtime.
