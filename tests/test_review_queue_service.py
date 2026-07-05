import tempfile
import unittest
from pathlib import Path

from src.vyu.authz import Principal, Role, WorkspaceMembership
from src.vyu.governance.box import GovernanceBox
from src.vyu.governance.trust import TrustScore
from src.vyu.review import (
    ReviewDecision,
    ReviewStatus,
    create_review_task,
    decide_queued_review_task,
    list_review_queue,
)
from src.vyu.storage import ProductionScope, ProductionStorage


class ReviewQueueServiceTests(unittest.TestCase):
    def test_reviewer_loads_scoped_pending_queue(self):
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
            not_required = create_review_task(
                run_id="run-not-required",
                governance_box=_governance_box(human_review_required=False),
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                created_at="2026-06-14T00:01:00Z",
            )
            out_of_scope = create_review_task(
                run_id="run-other",
                governance_box=_governance_box(human_review_required=True),
                tenant_id="tenant-b",
                workspace_id="workspace-a",
                created_at="2026-06-14T00:02:00Z",
            )
            storage.save_review_task(pending)
            storage.save_review_task(not_required)
            storage.save_review_task(out_of_scope)

            queue = list_review_queue(
                storage=storage,
                principal=_principal(Role.REVIEWER),
                scope=ProductionScope(
                    tenant_id="tenant-a",
                    workspace_id="workspace-a",
                ),
                status=ReviewStatus.PENDING,
            )

        self.assertEqual([pending.to_json()], [task.to_json() for task in queue])

    def test_researcher_cannot_load_review_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "production.sqlite")
            storage.initialize()

            with self.assertRaises(PermissionError):
                list_review_queue(
                    storage=storage,
                    principal=_principal(Role.RESEARCHER),
                    scope=ProductionScope(
                        tenant_id="tenant-a",
                        workspace_id="workspace-a",
                    ),
                )

    def test_reviewer_decides_queued_task_and_records_audit_event(self):
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

            result = decide_queued_review_task(
                storage=storage,
                principal=_principal(Role.REVIEWER),
                review_id="review-run-pending",
                decision=ReviewDecision.APPROVE,
                comment="Evidence reviewed for export.",
                decided_at="2026-06-14T00:05:00Z",
                audit_event_id="event-review-decision",
                audit_created_at="2026-06-14T00:05:01Z",
            )
            loaded = storage.get_review_task("review-run-pending")
            events = storage.list_audit_events(
                run_id="run-pending",
                event_type="review_decision_recorded",
            )

        self.assertEqual("approved", result.status.value)
        self.assertEqual(result.to_json(), loaded.to_json())
        self.assertEqual(1, len(events))
        self.assertEqual("event-review-decision", events[0].event_id)
        self.assertEqual("reviewer-user", events[0].payload["reviewer_id"])
        self.assertEqual("approve", events[0].payload["decision"])


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
