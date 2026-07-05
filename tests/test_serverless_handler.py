import json
import unittest

from src.vyu.deployment import (
    DeploymentHttpRequest,
    DeploymentHttpResponse,
    ServerlessDeploymentHandler,
    ServerlessHandlerConfig,
    serverless_handler_from_deployment_handler,
)
from src.vyu.deployment.api_service import FrameworkRequestError


class ServerlessDeploymentHandlerTests(unittest.TestCase):
    def test_handler_delegates_valid_event_to_service_shell(self):
        shell = _ShellStub(
            {
                "statusCode": 200,
                "headers": {"x-vyu-request-id": "request-1"},
                "body": json.dumps({"reason": "service_healthy"}),
                "isBase64Encoded": False,
            }
        )
        handler = ServerlessDeploymentHandler(
            shell,
            config=ServerlessHandlerConfig(
                extra_response_headers={"x-vyu-deployment-target": "serverless"}
            ),
        )
        event = {
            "httpMethod": "GET",
            "path": "/v1/health",
            "headers": {"x-vyu-request-id": "request-1"},
        }

        response = handler.handle(event)

        self.assertEqual([event], shell.events)
        self.assertEqual(200, response["statusCode"])
        self.assertEqual("request-1", response["headers"]["x-vyu-request-id"])
        self.assertEqual("serverless", response["headers"]["x-vyu-deployment-target"])

    def test_handler_is_callable_for_cloud_function_entrypoints(self):
        shell = _ShellStub(
            {
                "statusCode": 202,
                "headers": {},
                "body": json.dumps({"reason": "accepted"}),
                "isBase64Encoded": False,
            }
        )
        handler = ServerlessDeploymentHandler(shell)

        response = handler({"httpMethod": "GET", "path": "/v1/health"}, context=object())

        self.assertEqual(202, response["statusCode"])
        self.assertEqual("accepted", json.loads(response["body"])["reason"])

    def test_handler_returns_400_for_invalid_event_without_delegating(self):
        shell = _ShellStub({"statusCode": 200, "headers": {}, "body": "{}"})
        handler = ServerlessDeploymentHandler(
            shell,
            config=ServerlessHandlerConfig(default_request_id="generated-serverless"),
        )

        response = handler.handle(["not", "a", "mapping"])

        self.assertEqual([], shell.events)
        self.assertEqual(400, response["statusCode"])
        payload = json.loads(response["body"])
        self.assertEqual("generated-serverless", payload["request_id"])
        self.assertEqual("serverless_request_invalid", payload["reason"])
        self.assertIn("must be a mapping", payload["error"]["detail"])

    def test_handler_converts_framework_request_errors_to_400_envelope(self):
        shell = _FailingShell(FrameworkRequestError("Serverless event is missing an HTTP method."))
        handler = ServerlessDeploymentHandler(shell)
        event = {
            "path": "/v1/health",
            "headers": {"x-vyu-request-id": "request-from-header"},
        }

        response = handler.handle(event)

        self.assertEqual(400, response["statusCode"])
        self.assertEqual("request-from-header", response["headers"]["x-vyu-request-id"])
        payload = json.loads(response["body"])
        self.assertEqual("serverless_request_invalid", payload["reason"])
        self.assertIn("missing an HTTP method", payload["error"]["detail"])

    def test_handler_uses_gateway_request_id_when_request_header_is_absent(self):
        shell = _FailingShell(FrameworkRequestError("bad event"))
        handler = ServerlessDeploymentHandler(shell)

        response = handler.handle({"requestContext": {"requestId": "gateway-request-1"}})

        payload = json.loads(response["body"])
        self.assertEqual("gateway-request-1", payload["request_id"])
        self.assertEqual("gateway-request-1", response["headers"]["x-vyu-request-id"])

    def test_handler_hides_unhandled_exception_details_by_default(self):
        shell = _FailingShell(RuntimeError("database secret path leaked"))
        handler = ServerlessDeploymentHandler(shell)

        response = handler.handle({"httpMethod": "GET", "path": "/v1/health"})

        self.assertEqual(500, response["statusCode"])
        payload = json.loads(response["body"])
        self.assertEqual("serverless_handler_error", payload["reason"])
        self.assertEqual("Unhandled serverless handler error.", payload["error"]["detail"])

    def test_factory_wraps_deployment_http_handler(self):
        deployment_handler = _DeploymentHandlerStub(
            DeploymentHttpResponse(
                status_code=200,
                body={"reason": "service_healthy"},
                headers={"x-vyu-request-id": "request-factory"},
            )
        )
        handler = serverless_handler_from_deployment_handler(deployment_handler)

        response = handler.handle({"httpMethod": "GET", "path": "/v1/health"})

        self.assertEqual(200, response["statusCode"])
        self.assertEqual("service_healthy", json.loads(response["body"])["reason"])
        self.assertEqual("GET", deployment_handler.requests[0].method)
        self.assertEqual("/v1/health", deployment_handler.requests[0].path)


class _ShellStub:
    def __init__(self, response):
        self.response = response
        self.events = []

    def handle_serverless_event(self, event):
        self.events.append(event)
        return self.response


class _FailingShell:
    def __init__(self, error):
        self.error = error

    def handle_serverless_event(self, event):
        raise self.error


class _DeploymentHandlerStub:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def handle(self, request: DeploymentHttpRequest):
        self.requests.append(request)
        return self.response


if __name__ == "__main__":
    unittest.main()
