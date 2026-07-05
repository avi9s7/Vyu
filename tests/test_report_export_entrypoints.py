import tempfile
import unittest
from pathlib import Path

from src.vyu.authz import Principal, Role, WorkspaceMembership
from src.vyu.entrypoints import (
    ReportExportApiRequest,
    ReportExportPayload,
    ReportExportWorkerJob,
    handle_report_export_api,
    run_report_export_worker_job,
)
from src.vyu.generation import AnswerClaim, EvidenceContext, EvidenceItem, GroundedAnswer
from src.vyu.governance import GovernanceBox, TrustScore
from src.vyu.reports import ReportType
from src.vyu.review import create_review_task
from src.vyu.storage import ProductionStorage


class ReportExportEntrypointTests(unittest.TestCase):
    def test_api_adapter_calls_export_gate_and_returns_serializable_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "production.sqlite")
            storage.initialize()

            response = handle_report_export_api(
                ReportExportApiRequest(
                    request_id="api-request-001",
                    payload=_payload(
                        principal=_principal(Role.REVIEWER),
                        citation_ids=["CIT-001"],
                        passage_text="VX-101 reduced monthly migraine days.",
                    ),
                ),
                storage=storage,
                audit_event_id_factory=_audit_event_id,
                audit_created_at="2026-06-14T00:00:01Z",
            )
            events = storage.list_audit_events(run_id="run-001")

        self.assertEqual(200, response.status_code)
        self.assertEqual("api-request-001", response.body["request_id"])
        self.assertTrue(response.body["export"]["allowed"])
        self.assertEqual("export_allowed", response.body["export"]["reason"])
        self.assertIn("Research Report", response.body["export"]["content"])
        self.assertEqual(
            [
                "prompt_injection_decision_recorded",
                "citation_policy_decision_recorded",
                "report_export_decision_recorded",
            ],
            [event.event_type for event in events],
        )

    def test_api_adapter_returns_forbidden_when_export_gate_blocks(self):
        response = handle_report_export_api(
            ReportExportApiRequest(
                request_id="api-request-001",
                payload=_payload(
                    principal=_principal(Role.RESEARCHER),
                    citation_ids=["CIT-001"],
                    passage_text="VX-101 reduced monthly migraine days.",
                ),
            )
        )

        self.assertEqual(403, response.status_code)
        self.assertFalse(response.body["export"]["allowed"])
        self.assertEqual("export_not_authorized", response.body["export"]["reason"])

    def test_worker_adapter_calls_export_gate_and_marks_blocked_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "production.sqlite")
            storage.initialize()

            result = run_report_export_worker_job(
                ReportExportWorkerJob(
                    job_id="job-001",
                    payload=_payload(
                        principal=_principal(Role.REVIEWER),
                        citation_ids=["CIT-999"],
                        passage_text="VX-101 reduced monthly migraine days.",
                    ),
                ),
                storage=storage,
                audit_event_id_factory=_audit_event_id,
                audit_created_at="2026-06-14T00:00:01Z",
            )
            events = storage.list_audit_events(
                run_id="run-001",
                event_type="citation_policy_decision_recorded",
            )

        self.assertEqual("job-001", result.job_id)
        self.assertEqual("blocked", result.status)
        self.assertFalse(result.export["allowed"])
        self.assertEqual("citation_policy_blocked", result.export["reason"])
        self.assertIn("Invalid citations: CIT-999", result.export["details"])
        self.assertEqual(1, len(events))
        self.assertEqual("blocked", events[0].payload["status"])


def _payload(
    principal: Principal,
    citation_ids: list[str],
    passage_text: str,
) -> ReportExportPayload:
    box = _governance_box(human_review_required=False)
    return ReportExportPayload(
        principal=principal,
        report_type=ReportType.RESEARCH_REPORT,
        answer=_answer(citation_ids),
        context=_context(passage_text),
        trust_score=_trust(),
        governance_box=box,
        review_task=create_review_task(
            run_id="run-001",
            governance_box=box,
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            created_at="2026-06-14T00:00:00Z",
        ),
    )


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


def _answer(citation_ids: list[str]) -> GroundedAnswer:
    return GroundedAnswer(
        question="Does VX-101 reduce migraine days?",
        answer_text="VX-101 reduced monthly migraine days.",
        claims=(
            AnswerClaim(
                claim_id="CLM-001",
                text="VX-101 reduced monthly migraine days.",
                citation_ids=citation_ids,
            ),
        ),
        abstained=False,
    )


def _context(passage_text: str) -> EvidenceContext:
    return EvidenceContext(
        question="Does VX-101 reduce migraine days?",
        items=(
            EvidenceItem(
                citation_id="CIT-001",
                document_id="DOC-001",
                passage_id="PASS-001",
                title="VX-101 trial",
                passage_text=passage_text,
                retrieval_score=1.0,
                retrieval_source="bm25",
                is_retracted=False,
                is_preprint=False,
            ),
        ),
    )


def _trust() -> TrustScore:
    return TrustScore(overall=92, components={"citation_coverage": 100}, warnings=[])


def _governance_box(human_review_required: bool) -> GovernanceBox:
    return GovernanceBox(
        question="Does VX-101 reduce migraine days?",
        sources_searched=["dummy_corpus"],
        search_run_at="2026-06-14T00:00:00Z",
        retrieved_count=1,
        included_count=1,
        excluded_count=0,
        evidence_mix={"reviewed": 1},
        conflicts=[],
        models={"generator": "deterministic_grounded_answer_v1"},
        policy_versions={"governance_policy": "governance_policy_v1"},
        human_review_required=human_review_required,
        human_review_reason="No POC governance warnings",
        trust_score=_trust(),
    )


def _audit_event_id(_run_id: str, event_type: str) -> str:
    return f"event-{event_type}"


if __name__ == "__main__":
    unittest.main()
