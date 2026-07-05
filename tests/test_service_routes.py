import unittest

from src.vyu.entrypoints.report_export_routes import ReportExportRouteResponse
from src.vyu.entrypoints.review_queue_routes import ReviewQueueRouteResponse
from src.vyu.entrypoints.service_routes import (
    ServiceRouteRequest,
    ServiceRouteRuntime,
)


class _ReviewQueueStub:
    def __init__(self):
        self.requests = []

    def handle(self, request):
        self.requests.append(request)
        return ReviewQueueRouteResponse(
            status_code=200,
            body={
                "request_id": request.headers["x-vyu-request-id"],
                "reason": "review_queue_loaded",
                "review_tasks": [],
            },
        )


class _ReportExportStub:
    def __init__(self):
        self.requests = []

    def handle(self, request):
        self.requests.append(request)
        return ReportExportRouteResponse(
            status_code=403,
            body={
                "request_id": request.headers["x-vyu-request-id"],
                "reason": "review_required",
                "detail": "Review is still pending.",
            },
        )


class ServiceRouteRuntimeTests(unittest.TestCase):
    def test_health_route_returns_envelope_without_identity_headers(self):
        runtime = ServiceRouteRuntime(
            review_queue_runtime=_ReviewQueueStub(),
            report_export_runtime=_ReportExportStub(),
            request_id_factory=lambda: "request-001",
        )

        response = runtime.handle(
            ServiceRouteRequest(
                method="GET",
                path="/v1/health",
                headers={},
            )
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("request-001", response.body["request_id"])
        self.assertEqual("request-001", response.body["audit_correlation_id"])
        self.assertEqual("ok", response.body["status"])
        self.assertEqual("service_healthy", response.body["reason"])
        self.assertEqual("request-001", response.headers["x-vyu-request-id"])

    def test_review_queue_route_normalizes_headers_and_wraps_response(self):
        review_runtime = _ReviewQueueStub()
        runtime = ServiceRouteRuntime(
            review_queue_runtime=review_runtime,
            report_export_runtime=_ReportExportStub(),
            request_id_factory=lambda: "generated-request",
        )

        response = runtime.handle(
            ServiceRouteRequest(
                method="get",
                path="/v1/review-queue",
                headers={
                    "X-VYU-User-ID": "reviewer-1",
                    "X-VYU-Tenant-ID": "tenant-a",
                    "X-VYU-Workspace-ID": "workspace-a",
                    "X-VYU-Role": "reviewer",
                    "X-VYU-Request-ID": "request-123",
                    "X-VYU-Audit-Correlation-ID": "corr-123",
                },
                query={
                    "tenant_id": "tenant-a",
                    "workspace_id": "workspace-a",
                    "status": "pending",
                },
            )
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("request-123", response.body["request_id"])
        self.assertEqual("corr-123", response.body["audit_correlation_id"])
        self.assertEqual("ok", response.body["status"])
        self.assertEqual("review_queue_loaded", response.body["reason"])
        self.assertEqual("review_queue_loaded", response.body["data"]["reason"])
        self.assertEqual("request-123", review_runtime.requests[0].headers["x-vyu-request-id"])
        self.assertEqual("reviewer-1", review_runtime.requests[0].headers["x-vyu-user-id"])

    def test_report_export_route_wraps_forbidden_response_as_error_envelope(self):
        report_runtime = _ReportExportStub()
        runtime = ServiceRouteRuntime(
            review_queue_runtime=_ReviewQueueStub(),
            report_export_runtime=report_runtime,
            request_id_factory=lambda: "request-456",
        )

        response = runtime.handle(
            ServiceRouteRequest(
                method="POST",
                path="/v1/report-exports",
                headers=_identity_headers(),
                json_body={
                    "review_id": "review-1",
                    "report_type": "research_report",
                },
            )
        )

        self.assertEqual(403, response.status_code)
        self.assertEqual("error", response.body["status"])
        self.assertEqual("review_required", response.body["reason"])
        self.assertEqual("review_required", response.body["error"]["reason"])
        self.assertEqual("request-456", report_runtime.requests[0].headers["x-vyu-request-id"])

    def test_service_runtime_rejects_missing_identity_before_delegate(self):
        review_runtime = _ReviewQueueStub()
        runtime = ServiceRouteRuntime(
            review_queue_runtime=review_runtime,
            report_export_runtime=_ReportExportStub(),
            request_id_factory=lambda: "request-789",
        )

        response = runtime.handle(
            ServiceRouteRequest(
                method="GET",
                path="/v1/review-queue",
                headers={"x-vyu-user-id": "reviewer-1"},
                query={"tenant_id": "tenant-a", "workspace_id": "workspace-a"},
            )
        )

        self.assertEqual(401, response.status_code)
        self.assertEqual("identity_required", response.body["reason"])
        self.assertIn("x-vyu-tenant-id", response.body["error"]["detail"])
        self.assertEqual([], review_runtime.requests)

    def test_service_runtime_rejects_unknown_roles_and_routes(self):
        runtime = ServiceRouteRuntime(
            review_queue_runtime=_ReviewQueueStub(),
            report_export_runtime=_ReportExportStub(),
            request_id_factory=lambda: "request-999",
        )

        role_response = runtime.handle(
            ServiceRouteRequest(
                method="GET",
                path="/v1/review-queue",
                headers={**_identity_headers(), "x-vyu-role": "superuser"},
                query={"tenant_id": "tenant-a", "workspace_id": "workspace-a"},
            )
        )
        route_response = runtime.handle(
            ServiceRouteRequest(
                method="GET",
                path="/v1/unknown",
                headers={},
            )
        )

        self.assertEqual(401, role_response.status_code)
        self.assertEqual("identity_required", role_response.body["reason"])
        self.assertIn("Unknown Vyu role", role_response.body["error"]["detail"])
        self.assertEqual(404, route_response.status_code)
        self.assertEqual("route_not_found", route_response.body["reason"])


def _identity_headers():
    return {
        "x-vyu-user-id": "reviewer-1",
        "x-vyu-tenant-id": "tenant-a",
        "x-vyu-workspace-id": "workspace-a",
        "x-vyu-role": "reviewer",
    }


if __name__ == "__main__":
    unittest.main()
