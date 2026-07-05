import tempfile
import unittest
from pathlib import Path

from src.vyu.authz import Role
from src.vyu.entrypoints import (
    ReviewQueueRouteRequest,
    ReviewQueueRouteRuntime,
)
from src.vyu.governance.box import GovernanceBox
from src.vyu.governance.trust import TrustScore
from src.vyu.review import create_review_task
from src.vyu.storage import ProductionStorage


class ReviewQueueRouteTests(unittest.TestCase):
    def test_get_review_queue_route_lists_scoped_pending_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = _storage_with_pending_task(Path(tmp))
            runtime = ReviewQueueRouteRuntime(storage=storage)

            response = runtime.handle(
                ReviewQueueRouteRequest(
                    method="GET",
                    path="/v1/review-queue",
                    headers=_headers(Role.REVIEWER),
                    query={
                        "tenant_id": "tenant-a",
                        "workspace_id": "workspace-a",
                        "status": "pending",
                        "run_id": "run-pending",
                    },
                )
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("review_queue_loaded", response.body["reason"])
        self.assertEqual(1, len(response.body["review_tasks"]))
        self.assertEqual("review-run-pending", response.body["review_tasks"][0]["review_id"])

    def test_get_review_queue_route_returns_forbidden_for_unauthorized_role(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = _storage_with_pending_task(Path(tmp))
            runtime = ReviewQueueRouteRuntime(storage=storage)

            response = runtime.handle(
                ReviewQueueRouteRequest(
                    method="GET",
                    path="/v1/review-queue",
                    headers=_headers(Role.RESEARCHER),
                    query={
                        "tenant_id": "tenant-a",
                        "workspace_id": "workspace-a",
                    },
                )
            )

        self.assertEqual(403, response.status_code)
        self.assertEqual("review_queue_not_authorized", response.body["reason"])
        self.assertEqual([], response.body["review_tasks"])

    def test_post_review_decision_route_records_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = _storage_with_pending_task(Path(tmp))
            runtime = ReviewQueueRouteRuntime(
                storage=storage,
                audit_event_id_factory=lambda _run_id, event_type: f"event-{event_type}",
                audit_created_at="2026-06-15T00:06:00Z",
            )

            response = runtime.handle(
                ReviewQueueRouteRequest(
                    method="POST",
                    path="/v1/review-queue/review-run-pending/decision",
                    headers=_headers(Role.REVIEWER),
                    json_body={
                        "decision": "approve",
                        "comment": "Evidence reviewed for export.",
                        "decided_at": "2026-06-15T00:05:00Z",
                    },
                )
            )
            stored = storage.get_review_task("review-run-pending")
            events = storage.list_audit_events(
                run_id="run-pending",
                event_type="review_decision_recorded",
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("review_decision_recorded", response.body["reason"])
        self.assertEqual("approved", response.body["review_task"]["status"])
        self.assertEqual(stored.to_json(), response.body["review_task"])
        self.assertEqual(1, len(events))
        self.assertEqual("event-review_decision_recorded", events[0].event_id)

    def test_route_runtime_reports_unknown_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = _storage_with_pending_task(Path(tmp))
            runtime = ReviewQueueRouteRuntime(storage=storage)

            response = runtime.handle(
                ReviewQueueRouteRequest(
                    method="GET",
                    path="/v1/unknown",
                    headers=_headers(Role.REVIEWER),
                )
            )

        self.assertEqual(404, response.status_code)
        self.assertEqual("route_not_found", response.body["reason"])

    def test_route_runtime_reports_bad_request_for_missing_query_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = _storage_with_pending_task(Path(tmp))
            runtime = ReviewQueueRouteRuntime(storage=storage)

            response = runtime.handle(
                ReviewQueueRouteRequest(
                    method="GET",
                    path="/v1/review-queue",
                    headers=_headers(Role.REVIEWER),
                    query={"workspace_id": "workspace-a"},
                )
            )

        self.assertEqual(400, response.status_code)
        self.assertEqual("route_bad_request", response.body["reason"])
        self.assertIn("tenant_id", response.body["detail"])


def _storage_with_pending_task(tmp: Path) -> ProductionStorage:
    storage = ProductionStorage(tmp / "production.sqlite")
    storage.initialize()
    storage.save_review_task(
        create_review_task(
            run_id="run-pending",
            governance_box=_governance_box(),
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            created_at="2026-06-15T00:00:00Z",
        )
    )
    storage.save_review_task(
        create_review_task(
            run_id="run-other",
            governance_box=_governance_box(),
            tenant_id="tenant-b",
            workspace_id="workspace-a",
            created_at="2026-06-15T00:00:01Z",
        )
    )
    return storage


def _headers(role: Role) -> dict[str, str]:
    return {
        "x-vyu-user-id": f"{role.value}-user",
        "x-vyu-role": role.value,
        "x-vyu-tenant-id": "tenant-a",
        "x-vyu-workspace-id": "workspace-a",
    }


def _governance_box() -> GovernanceBox:
    return GovernanceBox(
        question="Does VX-101 reduce migraine days?",
        sources_searched=["dummy_corpus"],
        search_run_at="2026-06-15T00:00:00Z",
        retrieved_count=5,
        included_count=5,
        excluded_count=0,
        evidence_mix={"reviewed": 4, "preprint": 1},
        conflicts=[],
        models={"generator": "deterministic_grounded_answer_v1"},
        policy_versions={"governance_policy": "governance_policy_v1"},
        human_review_required=True,
        human_review_reason="Preprint evidence is present",
        trust_score=TrustScore(
            overall=84,
            components={"citation_coverage": 100},
            warnings=["Preprint evidence is present"],
        ),
    )


if __name__ == "__main__":
    unittest.main()
