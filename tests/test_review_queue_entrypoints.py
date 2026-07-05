import tempfile
import unittest
from pathlib import Path

from src.vyu.authz import Principal, Role, WorkspaceMembership
from src.vyu.entrypoints import (
    ReviewQueueDecisionPayload,
    ReviewQueueDecisionWorkerJob,
    ReviewQueueListApiRequest,
    ReviewQueueListPayload,
    handle_review_queue_list_api,
    run_review_queue_decision_worker_job,
)
from src.vyu.governance.box import GovernanceBox
from src.vyu.governance.trust import TrustScore
from src.vyu.review import ReviewDecision, ReviewStatus, create_review_task
from src.vyu.storage import ProductionStorage


class ReviewQueueEntrypointTests(unittest.TestCase):
    def test_api_adapter_lists_scoped_pending_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "production.sqlite")
            storage.initialize()
            pending = create_review_task(
                run_id="run-pending",
                governance_box=_governance_box(human_review_required=True),
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                created_at="2026-06-14T00:00:00Z",
            )
            storage.save_review_task(pending)
            storage.save_review_task(
                create_review_task(
                    run_id="run-other",
                    governance_box=_governance_box(human_review_required=True),
                    tenant_id="tenant-b",
                    workspace_id="workspace-a",
                    created_at="2026-06-14T00:01:00Z",
                )
            )

            response = handle_review_queue_list_api(
                ReviewQueueListApiRequest(
                    request_id="review-list-request-001",
                    payload=ReviewQueueListPayload(
                        principal=_principal(Role.REVIEWER),
                        tenant_id="tenant-a",
                        workspace_id="workspace-a",
                        status=ReviewStatus.PENDING,
                    ),
                ),
                storage=storage,
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("review-list-request-001", response.body["request_id"])
        self.assertEqual("tenant-a", response.body["tenant_id"])
        self.assertEqual(1, len(response.body["review_tasks"]))
        self.assertEqual(
            "review-run-pending",
            response.body["review_tasks"][0]["review_id"],
        )

    def test_api_adapter_returns_forbidden_when_queue_access_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "production.sqlite")
            storage.initialize()

            response = handle_review_queue_list_api(
                ReviewQueueListApiRequest(
                    request_id="review-list-request-001",
                    payload=ReviewQueueListPayload(
                        principal=_principal(Role.RESEARCHER),
                        tenant_id="tenant-a",
                        workspace_id="workspace-a",
                    ),
                ),
                storage=storage,
            )

        self.assertEqual(403, response.status_code)
        self.assertEqual("review_queue_not_authorized", response.body["reason"])
        self.assertEqual([], response.body["review_tasks"])

    def test_worker_adapter_records_review_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "production.sqlite")
            storage.initialize()
            task = create_review_task(
                run_id="run-pending",
                governance_box=_governance_box(human_review_required=True),
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                created_at="2026-06-14T00:00:00Z",
            )
            storage.save_review_task(task)

            result = run_review_queue_decision_worker_job(
                ReviewQueueDecisionWorkerJob(
                    job_id="review-decision-job-001",
                    payload=ReviewQueueDecisionPayload(
                        principal=_principal(Role.REVIEWER),
                        review_id="review-run-pending",
                        decision=ReviewDecision.APPROVE,
                        comment="Evidence reviewed for export.",
                        decided_at="2026-06-14T00:05:00Z",
                    ),
                ),
                storage=storage,
                audit_event_id_factory=_audit_event_id,
                audit_created_at="2026-06-14T00:05:01Z",
            )
            stored = storage.get_review_task("review-run-pending")
            events = storage.list_audit_events(
                run_id="run-pending",
                event_type="review_decision_recorded",
            )

        self.assertEqual("review-decision-job-001", result.job_id)
        self.assertEqual("completed", result.status)
        self.assertEqual("approved", result.review_task["status"])
        self.assertEqual(result.review_task, stored.to_json())
        self.assertEqual(1, len(events))
        self.assertEqual("event-review_decision_recorded", events[0].event_id)


def _principal(role: Role) -> Principal:
    return Principal(
        user_id=f"{role.value}-user",
        memberships=(
            WorkspaceMembership(
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                roles=(role,),
            ),
        ),
    )


def _audit_event_id(_run_id: str, event_type: str) -> str:
    return f"event-{event_type}"


def _governance_box(human_review_required: bool) -> GovernanceBox:
    return GovernanceBox(
        question="Does VX-101 reduce migraine days?",
        sources_searched=["dummy_corpus"],
        search_run_at="2026-06-14T00:00:00Z",
        retrieved_count=5,
        included_count=5,
        excluded_count=0,
        evidence_mix={"reviewed": 4, "preprint": 1},
        conflicts=[],
        models={"generator": "deterministic_grounded_answer_v1"},
        policy_versions={"governance_policy": "governance_policy_v1"},
        human_review_required=human_review_required,
        human_review_reason=(
            "Preprint evidence is present"
            if human_review_required
            else "No POC governance warnings"
        ),
        trust_score=TrustScore(
            overall=84 if human_review_required else 92,
            components={"citation_coverage": 100},
            warnings=["Preprint evidence is present"] if human_review_required else [],
        ),
    )


if __name__ == "__main__":
    unittest.main()
