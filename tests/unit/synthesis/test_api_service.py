from __future__ import annotations

import unittest
from unittest.mock import Mock
from uuid import uuid4

from src.vyu.auth.principal import RequestPrincipal
from src.vyu.model_gateway.contracts import ModelPolicy, ProviderHealth, ProviderHealthStatus
from src.vyu.model_gateway.gateway import ModelGateway
from src.vyu.synthesis.api_service import (
    SynthesisAnswerNotFound,
    SynthesisApiService,
    SynthesisForbidden,
    SynthesisResearchNotFound,
)
from src.vyu.synthesis.repository import (
    AnswerClaimDraft,
    AnswerRecord,
    ModelCallRecord,
    ModelCallMetrics,
    ModelPolicyRecord,
    PromptTemplateRecord,
)
from src.vyu.synthesis.settings import SynthesisApiSettings


def _principal(*, role: str = "reviewer") -> RequestPrincipal:
    return RequestPrincipal(
        user_id=uuid4(),
        issuer="https://local.vyu.invalid",
        subject="user-1",
        email="user@example.com",
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        role=role,
        authentication_method="local_hs256",
    )


class SynthesisApiServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = Mock()
        self.gateway = ModelGateway(
            policy=ModelPolicy(
                policy_version="1",
                allowed_providers=frozenset({"deterministic"}),
                allowed_models=frozenset({"vyu-deterministic-v1"}),
                allowed_use_cases=frozenset({"grounded_synthesis"}),
                allowed_prompt_versions=frozenset({"grounded_answer_v1"}),
            ),
            generation_adapters={},
            health_adapters={
                "deterministic": Mock(
                    health=Mock(
                        return_value=ProviderHealth(
                            provider_id="deterministic",
                            status=ProviderHealthStatus.HEALTHY,
                            checked_at="2026-07-08T00:00:00+00:00",
                            latency_ms=5,
                        )
                    )
                )
            },
        )
        self.service = SynthesisApiService(
            settings=SynthesisApiSettings(env="test"),
            repository=self.repository,
            gateway=self.gateway,
        )
        self.session = Mock()
        self.principal = _principal()

    def test_get_research_answer_maps_claims_without_provider_payload(self) -> None:
        research_run_id = uuid4()
        answer_id = uuid4()
        model_call_id = uuid4()
        self.service._get_research_run = Mock(return_value=Mock(id=research_run_id))
        self.repository.get_answer_for_research_run.return_value = AnswerRecord(
            answer_id=answer_id,
            tenant_id=self.principal.tenant_id,
            workspace_id=self.principal.workspace_id,
            research_run_id=research_run_id,
            retrieval_run_id=uuid4(),
            version=1,
            status="draft",
            answer_text="Summary text.",
            uncertainty="Some uncertainty.",
            limitations=("Limitation one.",),
            model_call_id=model_call_id,
            prompt_version="grounded_answer_v1",
            evidence_context_sha256="c" * 64,
            claims=(
                AnswerClaimDraft(
                    ordinal=1,
                    text="Claim text.",
                    support_status="supported",
                    citation_ids=("CIT-001",),
                ),
            ),
            created_at="2026-07-08T00:00:00+00:00",
        )
        self.repository.get_model_call.return_value = ModelCallRecord(
            call_id=model_call_id,
            tenant_id=self.principal.tenant_id,
            workspace_id=self.principal.workspace_id,
            run_id=str(research_run_id),
            job_id=None,
            provider_id="deterministic",
            model_id="vyu-deterministic-v1",
            prompt_template_id="grounded_answer",
            prompt_version="grounded_answer_v1",
            policy_version="1",
            request_sha256="d" * 64,
            response_sha256="e" * 64,
            evidence_context_sha256="c" * 64,
            provider_request_id="secret-provider-id",
            status="succeeded",
            safe_error_code=None,
            usage={},
            latency_ms=10,
            estimated_cost_minor=None,
            currency=None,
        )

        response = self.service.get_research_answer(
            search_id=research_run_id,
            version=None,
            principal=self.principal,
            session=self.session,
        )
        self.assertEqual("draft", response.status)
        self.assertEqual("deterministic", response.model_provider_id)
        self.assertEqual(["CIT-001"], response.claims[0].citation_ids)
        self.assertNotIn("provider_request_id", response.model_dump())

    def test_missing_research_run_raises_not_found(self) -> None:
        self.service._get_research_run = Mock(return_value=None)
        with self.assertRaises(SynthesisResearchNotFound):
            self.service.get_research_answer(
                search_id=uuid4(),
                version=None,
                principal=self.principal,
                session=self.session,
            )

    def test_missing_answer_raises_not_found(self) -> None:
        self.service._get_research_run = Mock(return_value=Mock(id=uuid4()))
        self.repository.get_answer_for_research_run.return_value = None
        with self.assertRaises(SynthesisAnswerNotFound):
            self.service.get_research_answer(
                search_id=uuid4(),
                version=None,
                principal=self.principal,
                session=self.session,
            )

    def test_admin_routes_require_admin_role(self) -> None:
        with self.assertRaises(SynthesisForbidden):
            self.service.get_gateway_overview(
                principal=_principal(role="reviewer"),
                session=self.session,
            )

    def test_admin_overview_returns_aggregate_metrics(self) -> None:
        self.repository.aggregate_model_call_metrics.return_value = ModelCallMetrics(
            total_calls=2,
            succeeded_calls=1,
            failed_calls=1,
            blocked_calls=0,
            total_input_tokens=20,
            total_output_tokens=10,
            total_estimated_cost_minor=15,
            average_latency_ms=12.5,
            errors_by_code={"gateway_timeout": 1},
        )
        self.repository.get_active_model_policy.return_value = ModelPolicyRecord(
            policy_id=uuid4(),
            version_number=3,
            status="active",
            allowed_providers=("deterministic",),
            allowed_models=("vyu-deterministic-v1",),
            use_cases=("grounded_synthesis",),
            limits={},
            fallback_rules={},
            sha256="a" * 64,
        )
        self.repository.list_prompt_templates.return_value = (
            PromptTemplateRecord(
                template_id=uuid4(),
                name="grounded_answer",
                use_case="grounded_synthesis",
                version=1,
                status="active",
                template="secret template",
                output_schema={"type": "object"},
                sha256="b" * 64,
            ),
        )
        overview = self.service.get_gateway_overview(
            principal=_principal(role="admin"),
            session=self.session,
        )
        self.assertEqual(3, overview.active_policy_version)
        self.assertEqual(1, overview.active_prompt_count)
        self.assertEqual(2, overview.metrics["total_calls"])


if __name__ == "__main__":
    unittest.main()
