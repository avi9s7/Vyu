# API Service Shell

The API service shell is the dependency-free framework adapter boundary for Vyu deployment wiring.

The implementation is `src/vyu/deployment/api_service.py`. It does not import FastAPI, Flask, or a cloud provider SDK. It converts framework-like request objects and serverless HTTP events into `DeploymentHttpRequest`, delegates to the deployment HTTP adapter, and converts `DeploymentHttpResponse` back into framework-neutral or serverless payloads.

## Adapter Contracts

Implemented conversion boundaries:

- FastAPI/Starlette request-like objects through `deployment_request_from_fastapi`.
- Flask request-like objects through `deployment_request_from_flask`.
- API Gateway-style serverless events through `deployment_request_from_serverless_event`.
- Framework-neutral responses through `FrameworkHttpResponse`.
- API Gateway-style responses through `serverless_response_from_deployment`.

Malformed framework or event shapes raise `FrameworkRequestError` before the deployment handler is called.

## Current Limits

- No web server is started here.
- No framework dependency is pinned here.
- No rate limiting, CORS, compression, OpenAPI generation, or middleware stack is implemented here.
- Provider-specific SSO/OIDC/SAML/JWKS validation remains outside this shell until the identity provider is selected.
