from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from src.vyu.db.session import TenantScope, build_engine, build_session_factory, transaction
from src.vyu.db.settings import DatabaseSettings
from src.vyu.jobs.models import ResearchRun
from src.vyu.retrieval.index_contracts import IndexManifest, IndexStatus
from src.vyu.retrieval.repository import RetrievalIndexRepository
from src.vyu.retrieval.models import RetrievalRun
from src.vyu.synthesis.models import ModelPolicyVersion
from src.vyu.synthesis.repository import AnswerClaimDraft, ModelSynthesisRepository


@pytest.fixture
def synthesis_factory(postgres_urls: dict[str, str]):
    return build_session_factory(
        build_engine(DatabaseSettings(database_url=postgres_urls["migration"]))
    )


def _seed_research_and_retrieval(scope: TenantScope, factory) -> tuple:
    research_run_id = uuid4()
    retrieval_run_id = uuid4()
    with transaction(factory, scope=scope) as session:
        session.add(
            ResearchRun(
                id=research_run_id,
                tenant_id=scope.tenant_id,
                workspace_id=scope.workspace_id,
                created_by=uuid4(),
                question="aspirin efficacy",
                intended_use="literature_search",
                requested_sources=["pubmed"],
                status="completed",
                cancel_requested=False,
                policy_version="source-policy-v1",
            )
        )
        manifest = IndexManifest(
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
            use_case="evidence_memory",
            source_ids=("pubmed",),
            document_versions=(),
            chunker_name="vyu_section_chunker",
            chunker_version="1.0.0",
            embedding_provider="deterministic",
            embedding_model="vyu-deterministic-v1",
            embedding_dimensions=1536,
            build_git_sha="test-sha",
            policy_version="source-policy-v1",
        )
        index = RetrievalIndexRepository().create_index(
            session,
            manifest=manifest,
            document_count=0,
            chunk_count=0,
            status=IndexStatus.ACTIVE,
        )
        session.add(
            RetrievalRun(
                id=retrieval_run_id,
                tenant_id=scope.tenant_id,
                workspace_id=scope.workspace_id,
                retrieval_run_key="retrieval-run-test-001",
                workflow_run_id=str(research_run_id),
                retrieval_index_id=index.index_id,
                user_id="user-1",
                topic="cardiology",
                question="aspirin efficacy",
                retrieval_mode="hybrid_rrf_v1",
                top_k=5,
                query_metadata_filter_json={},
                retriever_versions_json={"bm25": "v1"},
                latency_ms=10,
            )
        )
        session.flush()
    return research_run_id, retrieval_run_id


def test_repository_persists_policy_prompt_call_and_answer(synthesis_factory) -> None:
    scope = TenantScope(tenant_id=uuid4(), workspace_id=uuid4())
    research_run_id, retrieval_run_id = _seed_research_and_retrieval(scope, synthesis_factory)
    repository = ModelSynthesisRepository()
    with transaction(synthesis_factory, scope=scope) as session:
        policy = repository.create_model_policy_version(
            session,
            version_number=1,
            allowed_providers=("deterministic",),
            allowed_models=("vyu-deterministic-v1",),
            use_cases=("grounded_synthesis",),
            limits={"max_output_tokens": 1000},
            fallback_rules={},
            approved_by="tester",
            status="active",
        )
        prompt = repository.create_prompt_template(
            session,
            name="grounded_answer_v1",
            use_case="grounded_synthesis",
            version=1,
            template="Answer using evidence only.",
            output_schema={"type": "object"},
            approved_by="tester",
            status="active",
        )
        duplicate_policy = repository.create_model_policy_version(
            session,
            version_number=1,
            allowed_providers=("deterministic",),
            allowed_models=("vyu-deterministic-v1",),
            use_cases=("grounded_synthesis",),
            limits={"max_output_tokens": 1000},
            fallback_rules={},
        )
        model_call = repository.save_model_call(
            session,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
            run_id=str(research_run_id),
            job_id=None,
            provider_id="deterministic",
            model_id="vyu-deterministic-v1",
            prompt_template_id=str(prompt.template_id),
            prompt_version="1",
            policy_version=str(policy.version_number),
            request_sha256="a" * 64,
            response_sha256="b" * 64,
            evidence_context_sha256="c" * 64,
            provider_request_id="provider-req-1",
            status="succeeded",
            safe_error_code=None,
            usage={"input_tokens": 10, "output_tokens": 5},
            latency_ms=20,
            estimated_cost_minor=12,
            currency="USD",
        )
        answer = repository.save_answer(
            session,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
            research_run_id=research_run_id,
            retrieval_run_id=retrieval_run_id,
            version=1,
            status="approved",
            answer_text="Aspirin reduces cardiovascular risk in selected populations.",
            uncertainty="Population-specific effect sizes vary.",
            limitations=("Observational evidence included",),
            model_call_id=model_call.call_id,
            prompt_version="1",
            evidence_context_sha256="c" * 64,
            claims=(
                AnswerClaimDraft(
                    ordinal=1,
                    text="Aspirin reduces cardiovascular risk.",
                    support_status="supported",
                    citation_ids=("doc:test:v:1:chunk:0",),
                ),
            ),
        )
        duplicate_call = repository.save_model_call(
            session,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
            run_id=str(research_run_id),
            job_id=None,
            provider_id="deterministic",
            model_id="vyu-deterministic-v1",
            prompt_template_id=str(prompt.template_id),
            prompt_version="1",
            policy_version=str(policy.version_number),
            request_sha256="a" * 64,
            response_sha256="b" * 64,
            evidence_context_sha256="c" * 64,
            provider_request_id="provider-req-1",
            status="succeeded",
            safe_error_code=None,
            usage={"input_tokens": 10, "output_tokens": 5},
            latency_ms=20,
        )
        policy_rows = session.scalars(select(ModelPolicyVersion)).all()

    assert policy.policy_id == duplicate_policy.policy_id
    assert model_call.call_id == duplicate_call.call_id
    assert answer.version == 1
    assert len(answer.claims) == 1
    assert answer.claims[0].citation_ids == ("doc:test:v:1:chunk:0",)
    assert len(policy_rows) == 1
