from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from datetime import UTC, datetime
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

from src.vyu.jobs.contracts import JobRecord
from src.vyu.jobs.models import ResearchRun
from src.vyu.model_gateway.contracts import ModelPolicy, ModelRequest, ModelResponse
from src.vyu.model_gateway.errors import (
    GatewayAuthenticationError,
    GatewayMalformedResponse,
    GatewayPolicyBlocked,
)
from src.vyu.model_gateway.gateway import ModelGateway
from src.vyu.synthesis.context import BuiltEvidenceContext, EvidenceContextItem
from src.vyu.synthesis.contracts import (
    EVIDENCE_CONTEXT_BUILDER_VERSION,
    GROUNDED_ANSWER_SCHEMA_VERSION,
)
from src.vyu.synthesis.repository import AnswerRecord, ModelCallRecord, ModelPolicyRecord
from src.vyu.synthesis.service import SynthesisExecutor, SynthesisSettings


def _valid_output() -> dict[str, object]:
    return {
        "answer_summary": "Aspirin reduced cardiovascular events in the cited trial.",
        "claims": [
            {
                "claim_text": "Aspirin reduced cardiovascular events.",
                "citation_ids": ["CIT-001"],
                "support": "supported",
            }
        ],
        "uncertainty": "Single trial evidence.",
        "contradictions": [],
        "limitations": [],
        "abstained": False,
        "abstention_reason": None,
    }


@dataclass
class FakeGenerationAdapter:
    provider_id: str = "deterministic"
    responses: list[dict[str, object] | Exception] = field(default_factory=list)
    calls: list[ModelRequest] = field(default_factory=list)

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        if not self.responses:
            raise RuntimeError("no fake responses configured")
        next_item = self.responses.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return ModelResponse.from_output(
            request=request,
            provider_request_id="provider-1",
            output=next_item,
            input_tokens=10,
            output_tokens=20,
            latency_ms=12,
            finish_reason="stop",
            schema_valid=True,
        )


def _policy_record() -> ModelPolicyRecord:
    return ModelPolicyRecord(
        policy_id=uuid4(),
        version_number=1,
        status="active",
        allowed_providers=("deterministic", "fallback"),
        allowed_models=("vyu-deterministic-v1",),
        use_cases=("grounded_synthesis",),
        limits={
            "max_output_tokens": 1000,
            "max_answer_chars": 10_000,
            "max_claims": 10,
            "allow_schema_repair": True,
        },
        fallback_rules={
            "allow_schema_repair": True,
            "generation_provider_fallback": {"deterministic": "fallback"},
        },
        sha256="a" * 64,
    )


def _context() -> BuiltEvidenceContext:
    return BuiltEvidenceContext(
        builder_version=EVIDENCE_CONTEXT_BUILDER_VERSION,
        research_run_id=uuid4(),
        retrieval_run_id=uuid4(),
        retrieval_index_id=uuid4(),
        policy_version="policy-v1",
        manifest_checksum="manifest",
        items=(
            EvidenceContextItem(
                citation_id="CIT-001",
                title="Trial",
                source_id="pubmed",
                source_date="2024",
                evidence_type="rct",
                evidence_quality="high",
                is_retracted=False,
                has_correction=False,
                excerpt="Aspirin reduced cardiovascular events in selected adults.",
                document_id="DOC-1",
                document_version_id=uuid4(),
                document_chunk_id=uuid4(),
                location="abstract",
                rank=1,
                token_count=10,
            ),
        ),
        exclusions=(),
        context_sha256="c" * 64,
        token_count=10,
    )


def _job(*, research_run_id: UUID, retrieval_run_id: UUID, payload: dict[str, object] | None = None) -> JobRecord:
    now = datetime.now(tz=UTC)
    return JobRecord(
        id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        kind="synthesis.run",
        status="running",
        attempt=1,
        max_attempts=3,
        payload={
            "research_run_id": str(research_run_id),
            "retrieval_run_id": str(retrieval_run_id),
            **(payload or {}),
        },
        result=None,
        error_code=None,
        available_at=now,
        leased_until=None,
        lease_owner="worker",
        created_at=now,
        updated_at=now,
        started_at=now,
        completed_at=None,
    )


class SynthesisServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.research_run_id = uuid4()
        self.retrieval_run_id = uuid4()
        self.adapter = FakeGenerationAdapter()
        self.gateway = ModelGateway(
            policy=ModelPolicy(
                policy_version="1",
                allowed_providers=frozenset({"deterministic", "fallback"}),
                allowed_models=frozenset({"vyu-deterministic-v1"}),
                allowed_use_cases=frozenset({"grounded_synthesis"}),
                allowed_prompt_versions=frozenset({GROUNDED_ANSWER_SCHEMA_VERSION}),
                max_output_tokens=1000,
                max_context_bytes=100_000,
                max_output_schema_properties=64,
            ),
            generation_adapters={
                "deterministic": self.adapter,
                "fallback": self.adapter,
            },
        )
        self.repository = Mock()
        self.research_repository = Mock()
        self.context_builder = Mock()
        self.executor = SynthesisExecutor(
            gateway=self.gateway,
            repository=self.repository,
            research_repository=self.research_repository,
            context_builder=self.context_builder,
            settings=SynthesisSettings(),
        )
        self.run = ResearchRun(
            id=self.research_run_id,
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            created_by=uuid4(),
            question="Does aspirin help?",
            intended_use="literature_search",
            requested_sources=["pubmed"],
            status="retrieving",
            cancel_requested=False,
            policy_version="policy-v1",
        )
        self.research_repository.get_run.return_value = self.run
        self.repository.get_active_model_policy.return_value = _policy_record()
        self.context_builder.build_from_session.return_value = _context()
        self.repository.next_answer_version.return_value = 1
        self.repository.save_model_call.return_value = ModelCallRecord(
            call_id=uuid4(),
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            run_id=str(self.research_run_id),
            job_id=None,
            provider_id="deterministic",
            model_id="vyu-deterministic-v1",
            prompt_template_id="grounded_answer",
            prompt_version=GROUNDED_ANSWER_SCHEMA_VERSION,
            policy_version="1",
            request_sha256="d" * 64,
            response_sha256="e" * 64,
            evidence_context_sha256="c" * 64,
            provider_request_id="provider-1",
            status="succeeded",
            safe_error_code=None,
            usage={},
            latency_ms=10,
            estimated_cost_minor=None,
            currency=None,
        )
        self.repository.save_answer.return_value = AnswerRecord(
            answer_id=uuid4(),
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            research_run_id=self.research_run_id,
            retrieval_run_id=self.retrieval_run_id,
            version=1,
            status="draft",
            answer_text="Aspirin reduced cardiovascular events in the cited trial.",
            uncertainty="Single trial evidence.",
            limitations=(),
            model_call_id=uuid4(),
            prompt_version=GROUNDED_ANSWER_SCHEMA_VERSION,
            evidence_context_sha256="c" * 64,
            claims=(),
        )

    def _response(self, output: dict[str, object] | None = None) -> dict[str, object]:
        return output or _valid_output()

    @patch("src.vyu.synthesis.service.AuditRepository")
    def test_valid_answer_completes_and_enqueues_governance(self, audit_repo: Mock) -> None:
        audit_repo.return_value.append.return_value = None
        self.adapter.responses = [self._response()]
        session = Mock()
        result = self.executor.execute(
            _job(
                research_run_id=self.research_run_id,
                retrieval_run_id=self.retrieval_run_id,
            ),
            session=session,
            heartbeat=lambda: None,
        )
        self.assertEqual("complete", result.outcome)
        self.assertEqual("review_required", result.result["status"])
        self.repository.save_answer.assert_called_once()
        session.add.assert_called()

    @patch("src.vyu.synthesis.service.AuditRepository")
    def test_empty_context_abstains_deterministically(self, audit_repo: Mock) -> None:
        audit_repo.return_value.append.return_value = None
        empty = BuiltEvidenceContext(
            builder_version=EVIDENCE_CONTEXT_BUILDER_VERSION,
            research_run_id=self.research_run_id,
            retrieval_run_id=self.retrieval_run_id,
            retrieval_index_id=uuid4(),
            policy_version="policy-v1",
            manifest_checksum="manifest",
            items=(),
            exclusions=(),
            context_sha256="c" * 64,
            token_count=0,
        )
        self.context_builder.build_from_session.return_value = empty
        result = self.executor.execute(
            _job(
                research_run_id=self.research_run_id,
                retrieval_run_id=self.retrieval_run_id,
            ),
            session=Mock(),
            heartbeat=lambda: None,
        )
        self.assertEqual("complete", result.outcome)
        self.assertTrue(result.result["abstained"])
        self.assertEqual([], self.adapter.calls)

    def test_model_refusal_blocks_without_repair(self) -> None:
        self.adapter.responses = [GatewayPolicyBlocked("refused")]
        result = self.executor.execute(
            _job(
                research_run_id=self.research_run_id,
                retrieval_run_id=self.retrieval_run_id,
            ),
            session=Mock(),
            heartbeat=lambda: None,
        )
        self.assertEqual("terminal_failure", result.outcome)
        self.repository.save_answer.assert_not_called()

    @patch("src.vyu.synthesis.service.AuditRepository")
    def test_malformed_output_can_attempt_schema_repair(self, audit_repo: Mock) -> None:
        audit_repo.return_value.append.return_value = None
        self.adapter.responses = [
            GatewayMalformedResponse("bad json"),
            self._response(),
        ]
        result = self.executor.execute(
            _job(
                research_run_id=self.research_run_id,
                retrieval_run_id=self.retrieval_run_id,
            ),
            session=Mock(),
            heartbeat=lambda: None,
        )
        self.assertEqual("complete", result.outcome)
        self.assertEqual(2, len(self.adapter.calls))
        self.assertIn(":repair", self.adapter.calls[1].request_id)

    @patch("src.vyu.synthesis.service.AuditRepository")
    def test_provider_fallback_uses_second_provider(self, audit_repo: Mock) -> None:
        audit_repo.return_value.append.return_value = None
        self.adapter.responses = [
            GatewayAuthenticationError("primary failed"),
            self._response(),
        ]
        policy = _policy_record()
        policy = ModelPolicyRecord(
            policy_id=policy.policy_id,
            version_number=policy.version_number,
            status=policy.status,
            allowed_providers=policy.allowed_providers,
            allowed_models=policy.allowed_models,
            use_cases=policy.use_cases,
            limits=policy.limits,
            fallback_rules={
                "allow_schema_repair": False,
                "generation_provider_fallback": {"deterministic": "fallback"},
            },
            sha256=policy.sha256,
        )
        self.repository.get_active_model_policy.return_value = policy
        result = self.executor.execute(
            _job(
                research_run_id=self.research_run_id,
                retrieval_run_id=self.retrieval_run_id,
            ),
            session=Mock(),
            heartbeat=lambda: None,
        )
        self.assertEqual("complete", result.outcome)
        self.assertEqual("fallback", self.adapter.calls[-1].provider_id)

    @patch("src.vyu.synthesis.service.AuditRepository")
    def test_audit_failure_leaves_terminal_failure(self, audit_repo: Mock) -> None:
        audit_repo.return_value.append.return_value = None
        self.adapter.responses = [self._response()]
        result = self.executor.execute(
            _job(
                research_run_id=self.research_run_id,
                retrieval_run_id=self.retrieval_run_id,
                payload={"fail_audit": True},
            ),
            session=Mock(),
            heartbeat=lambda: None,
        )
        self.assertEqual("terminal_failure", result.outcome)
        self.assertEqual("audit_persist_failed", result.error_code)

    def test_unknown_citation_fails_validation(self) -> None:
        bad_output = _valid_output()
        bad_output["claims"] = [
            {
                "claim_text": "Unsupported.",
                "citation_ids": ["CIT-999"],
                "support": "supported",
            }
        ]
        self.adapter.responses = [self._response(bad_output), self._response(bad_output)]
        result = self.executor.execute(
            _job(
                research_run_id=self.research_run_id,
                retrieval_run_id=self.retrieval_run_id,
            ),
            session=Mock(),
            heartbeat=lambda: None,
        )
        self.assertEqual("terminal_failure", result.outcome)
        self.repository.save_answer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
