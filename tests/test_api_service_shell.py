import asyncio
import base64
import json
import unittest

from src.vyu.deployment import (
    DeploymentApiServiceShell,
    DeploymentHttpRequest,
    DeploymentHttpResponse,
    FrameworkRequestError,
    deployment_request_from_fastapi,
    deployment_request_from_flask,
    deployment_request_from_serverless_event,
    serverless_response_from_deployment,
)


class ApiServiceShellTests(unittest.TestCase):
    def test_fastapi_request_is_converted_and_delegated(self):
        handler = _DeploymentHandlerStub(
            DeploymentHttpResponse(
                status_code=202,
                body={"status": "ok", "reason": "accepted"},
                headers={"x-vyu-request-id": "request-fastapi"},
            )
        )
        shell = DeploymentApiServiceShell(handler)
        request = _FastApiRequest(
            method="POST",
            path="/v1/report-exports",
            headers={"Authorization": "Bearer token", "X-VYU-Request-ID": "request-fastapi"},
            query_params={"tenant_id": "tenant-a"},
            body={"review_id": "review-1", "report_type": "research_report"},
        )

        response = asyncio.run(shell.handle_fastapi_request(request))

        delegated = handler.requests[0]
        self.assertEqual("POST", delegated.method)
        self.assertEqual("/v1/report-exports", delegated.path)
        self.assertEqual("Bearer token", delegated.headers["Authorization"])
        self.assertEqual({"tenant_id": "tenant-a"}, delegated.query)
        self.assertEqual("review-1", delegated.json_body["review_id"])
        self.assertEqual(202, response.status_code)
        self.assertEqual({"status": "ok", "reason": "accepted"}, response.body)
        self.assertEqual(
            {
                "status_code": 202,
                "content": {"status": "ok", "reason": "accepted"},
                "headers": {"x-vyu-request-id": "request-fastapi"},
            },
            response.as_json_response_kwargs(),
        )

    def test_flask_request_is_converted_and_delegated(self):
        handler = _DeploymentHandlerStub(
            DeploymentHttpResponse(status_code=200, body={"reason": "review_queue_loaded"})
        )
        shell = DeploymentApiServiceShell(handler)
        request = _FlaskRequest(
            method="GET",
            path="/v1/review-queue",
            headers={"authorization": "Bearer token"},
            args={"tenant_id": "tenant-a", "workspace_id": "workspace-a"},
            body=None,
        )

        response = shell.handle_flask_request(request)

        delegated = handler.requests[0]
        self.assertEqual("GET", delegated.method)
        self.assertEqual("/v1/review-queue", delegated.path)
        self.assertEqual({"tenant_id": "tenant-a", "workspace_id": "workspace-a"}, delegated.query)
        self.assertEqual({}, delegated.json_body)
        self.assertEqual(200, response.status_code)
        self.assertEqual("review_queue_loaded", response.body["reason"])

    def test_serverless_event_is_converted_to_request_and_response(self):
        handler = _DeploymentHandlerStub(
            DeploymentHttpResponse(
                status_code=401,
                body={"status": "error", "reason": "auth_token_invalid"},
                headers={"x-vyu-request-id": "request-serverless"},
            )
        )
        shell = DeploymentApiServiceShell(handler)
        encoded_body = base64.b64encode(
            json.dumps({"review_id": "review-1"}).encode("utf-8")
        ).decode("ascii")
        event = {
            "requestContext": {"http": {"method": "POST", "path": "/v1/report-exports"}},
            "rawPath": "/v1/report-exports",
            "rawQueryString": "tenant_id=tenant-a&workspace_id=workspace-a",
            "headers": {"authorization": "Bearer bad-token"},
            "body": encoded_body,
            "isBase64Encoded": True,
        }

        response = shell.handle_serverless_event(event)

        delegated = handler.requests[0]
        self.assertEqual("POST", delegated.method)
        self.assertEqual("/v1/report-exports", delegated.path)
        self.assertEqual({"tenant_id": "tenant-a", "workspace_id": "workspace-a"}, delegated.query)
        self.assertEqual({"review_id": "review-1"}, delegated.json_body)
        self.assertEqual(401, response["statusCode"])
        self.assertEqual(False, response["isBase64Encoded"])
        self.assertEqual("application/json", response["headers"]["content-type"])
        self.assertEqual("auth_token_invalid", json.loads(response["body"])["reason"])

    def test_serverless_rest_v1_event_uses_http_method_path_and_query_parameters(self):
        event = {
            "httpMethod": "GET",
            "path": "/v1/health",
            "queryStringParameters": {"verbose": "true"},
            "headers": {"x-vyu-request-id": "request-1"},
        }

        request = deployment_request_from_serverless_event(event)

        self.assertEqual("GET", request.method)
        self.assertEqual("/v1/health", request.path)
        self.assertEqual({"verbose": "true"}, request.query)
        self.assertEqual({}, request.json_body)

    def test_invalid_json_shapes_fail_before_delegation(self):
        with self.assertRaisesRegex(FrameworkRequestError, "must be an object"):
            deployment_request_from_serverless_event(
                {"httpMethod": "POST", "path": "/v1/report-exports", "body": "[]"}
            )

        with self.assertRaisesRegex(FrameworkRequestError, "missing an HTTP method"):
            deployment_request_from_serverless_event({"path": "/v1/health"})

    def test_conversion_helpers_can_be_used_without_shell(self):
        fastapi_request = _FastApiRequest(
            method="GET",
            path="/v1/health",
            headers={},
            query_params={},
            body=None,
        )
        flask_request = _FlaskRequest(
            method="GET",
            path="/v1/health",
            headers={},
            args={},
            body={},
        )

        converted_fastapi = asyncio.run(deployment_request_from_fastapi(fastapi_request))
        converted_flask = deployment_request_from_flask(flask_request)
        serverless_payload = serverless_response_from_deployment(
            DeploymentHttpResponse(status_code=200, body={"reason": "service_healthy"})
        )

        self.assertEqual("/v1/health", converted_fastapi.path)
        self.assertEqual("/v1/health", converted_flask.path)
        self.assertEqual(200, serverless_payload["statusCode"])
        self.assertEqual("service_healthy", json.loads(serverless_payload["body"])["reason"])


class _DeploymentHandlerStub:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def handle(self, request: DeploymentHttpRequest) -> DeploymentHttpResponse:
        self.requests.append(request)
        return self.response


class _Url:
    def __init__(self, path):
        self.path = path


class _FastApiRequest:
    def __init__(self, method, path, headers, query_params, body):
        self.method = method
        self.url = _Url(path)
        self.headers = headers
        self.query_params = query_params
        self._body = body

    async def json(self):
        return self._body


class _FlaskRequest:
    def __init__(self, method, path, headers, args, body):
        self.method = method
        self.path = path
        self.headers = headers
        self.args = args
        self._body = body

    def get_json(self, silent=True):
        return self._body


if __name__ == "__main__":
    unittest.main()
