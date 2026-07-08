from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import sessionmaker

from src.vyu.db.session import TenantScope, build_engine, build_session_factory, transaction
from src.vyu.db.settings import DatabaseSettings
from src.vyu.jobs.models import ResearchRun
from src.vyu.retrieval.index_contracts import IndexManifest, IndexStatus
from src.vyu.retrieval.models import RetrievalRun
from src.vyu.retrieval.repository import RetrievalIndexRepository
from src.vyu.synthesis.repository import AnswerClaimDraft, ModelSynthesisRepository
from tests.api.support import AuthTestContext, auth_headers, build_auth_test_client


def _seed_answer(
    factory: sessionmaker,
    scope: TenantScope,
    *,
    status: str = "draft",
    version: int = 1,
    research_run_id: UUID | None = None,
    create_run: bool = True,
) -> UUID:
    research_run_id = research_run_id or uuid4()
    retrieval_run_id = uuid4()
    repository = ModelSynthesisRepository()
    with transaction(factory, scope=scope) as session:
        if create_run:
            session.add(
                ResearchRun(
                    id=research_run_id,
                    tenant_id=scope.tenant_id,
                    workspace_id=scope.workspace_id,
                    created_by=uuid4(),
                    question="Does aspirin reduce cardiovascular risk?",
                    intended_use="literature_search",
                    requested_sources=["pubmed"],
                    status="review_required",
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
                retrieval_run_key=f"retrieval-{version}",
                workflow_run_id=str(research_run_id),
                retrieval_index_id=index.index_id,
                user_id="user-1",
                topic="cardiology",
                question="Does aspirin reduce cardiovascular risk?",
                retrieval_mode="hybrid_rrf_v1",
                top_k=5,
                query_metadata_filter_json={},
                retriever_versions_json={"bm25": "v1"},
                latency_ms=10,
            )
        )
        policy = repository.get_active_model_policy(session)
        prompt_records = repository.list_prompt_templates(session)
        if policy is None or not prompt_records:
            policy = repository.create_model_policy_version(
                session,
                version_number=version,
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
                name="grounded_answer",
                use_case="grounded_synthesis",
                version=version,
                template="Answer using evidence only.",
                output_schema={"type": "object"},
                approved_by="tester",
                status="active",
            )
        else:
            prompt = prompt_records[0]
        model_call = repository.save_model_call(
            session,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
            run_id=str(research_run_id),
            job_id=None,
            provider_id="deterministic",
            model_id="vyu-deterministic-v1",
            prompt_template_id=str(prompt.template_id),
            prompt_version="grounded_answer_v1",
            policy_version=str(policy.version_number),
            request_sha256=f"{research_run_id.hex}-{version:064x}",
            response_sha256=f"{research_run_id.hex}-resp-{version:064x}",
            evidence_context_sha256=f"{research_run_id.hex}-ctx-{version:064x}",
            provider_request_id="provider-req-1",
            status="blocked" if status == "blocked" else "succeeded",
            safe_error_code="synthesis_validation_failed" if status == "blocked" else None,
            usage={"input_tokens": 10, "output_tokens": 5},
            latency_ms=20,
        )
        repository.save_answer(
            session,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
            research_run_id=research_run_id,
            retrieval_run_id=retrieval_run_id,
            version=version,
            status=status,
            answer_text="Aspirin reduced cardiovascular risk in the cited trial.",
            uncertainty="Single trial evidence.",
            limitations=("Pilot synthesis only.",),
            model_call_id=model_call.call_id,
            prompt_version="grounded_answer_v1",
            evidence_context_sha256=f"{version + 2:064x}",
            claims=(
                AnswerClaimDraft(
                    ordinal=1,
                    text="Aspirin reduced cardiovascular risk.",
                    support_status="supported",
                    citation_ids=("doc:test:v:1:chunk:0",),
                ),
            ),
        )
        session.flush()
    return research_run_id


@pytest.fixture
def synthesis_context(postgres_urls: dict[str, str]) -> AuthTestContext:
    return build_auth_test_client(postgres_urls, role="reviewer")


@pytest.fixture
def admin_context(postgres_urls: dict[str, str]) -> AuthTestContext:
    return build_auth_test_client(postgres_urls, role="admin")


def test_get_answer_returns_grounded_payload(
    postgres_urls: dict[str, str],
    synthesis_context: AuthTestContext,
) -> None:
    migration_factory = build_session_factory(
        build_engine(DatabaseSettings(database_url=postgres_urls["migration"]))
    )
    scope = TenantScope(
        tenant_id=synthesis_context.tenant_id,
        workspace_id=synthesis_context.workspace_id,
    )
    research_run_id = _seed_answer(migration_factory, scope)

    response = synthesis_context.client.get(
        f"/v1/research/searches/{research_run_id}/answer",
        headers=auth_headers(synthesis_context),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "draft"
    assert payload["version"] == 1
    assert payload["answer_summary"].startswith("Aspirin")
    assert payload["claims"][0]["citation_ids"] == ["doc:test:v:1:chunk:0"]
    assert payload["model_provider_id"] == "deterministic"
    assert "template" not in payload
    assert "provider_request_id" not in payload
    assert payload["links"]["review_queue"].endswith(str(research_run_id))


def test_missing_answer_returns_404(synthesis_context: AuthTestContext) -> None:
    response = synthesis_context.client.get(
        f"/v1/research/searches/{uuid4()}/answer",
        headers=auth_headers(synthesis_context),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_blocked_answer_is_returned_safely(
    postgres_urls: dict[str, str],
    synthesis_context: AuthTestContext,
) -> None:
    migration_factory = build_session_factory(
        build_engine(DatabaseSettings(database_url=postgres_urls["migration"]))
    )
    scope = TenantScope(
        tenant_id=synthesis_context.tenant_id,
        workspace_id=synthesis_context.workspace_id,
    )
    research_run_id = _seed_answer(migration_factory, scope, status="blocked")

    response = synthesis_context.client.get(
        f"/v1/research/searches/{research_run_id}/answer",
        headers=auth_headers(synthesis_context),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "blocked"


def test_answer_version_selection(
    postgres_urls: dict[str, str],
    synthesis_context: AuthTestContext,
) -> None:
    migration_factory = build_session_factory(
        build_engine(DatabaseSettings(database_url=postgres_urls["migration"]))
    )
    scope = TenantScope(
        tenant_id=synthesis_context.tenant_id,
        workspace_id=synthesis_context.workspace_id,
    )
    research_run_id = _seed_answer(migration_factory, scope, version=1)
    _seed_answer(
        migration_factory,
        scope,
        version=2,
        research_run_id=research_run_id,
        create_run=False,
    )

    latest = synthesis_context.client.get(
        f"/v1/research/searches/{research_run_id}/answer",
        headers=auth_headers(synthesis_context),
    )
    assert latest.status_code == 200
    assert latest.json()["version"] == 2

    first = synthesis_context.client.get(
        f"/v1/research/searches/{research_run_id}/answer?version=1",
        headers=auth_headers(synthesis_context),
    )
    assert first.status_code == 200
    assert first.json()["version"] == 1


def test_admin_overview_requires_admin_role(synthesis_context: AuthTestContext) -> None:
    response = synthesis_context.client.get(
        "/v1/admin/model-gateway/overview",
        headers=auth_headers(synthesis_context),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_admin_can_list_policies_and_activate_with_idempotency(
    postgres_urls: dict[str, str],
    admin_context: AuthTestContext,
) -> None:
    migration_factory = build_session_factory(
        build_engine(DatabaseSettings(database_url=postgres_urls["migration"]))
    )
    scope = TenantScope(tenant_id=admin_context.tenant_id, workspace_id=admin_context.workspace_id)
    _seed_answer(migration_factory, scope)

    overview = admin_context.client.get(
        "/v1/admin/model-gateway/overview",
        headers=auth_headers(admin_context),
    )
    assert overview.status_code == 200
    assert overview.json()["metrics"]["total_calls"] >= 1

    policies = admin_context.client.get(
        "/v1/admin/model-gateway/policies",
        headers=auth_headers(admin_context),
    )
    assert policies.status_code == 200
    assert policies.json()["items"]

    policy_id = policies.json()["items"][0]["policy_id"]
    body = {
        "reason": "Staging evaluation passed for pilot policy.",
        "approved_evaluation_id": "eval-pilot-001",
    }
    first = admin_context.client.post(
        f"/v1/admin/model-gateway/policies/{policy_id}/activate",
        headers=auth_headers(admin_context, idempotency_key="activate-policy-1"),
        json=body,
    )
    second = admin_context.client.post(
        f"/v1/admin/model-gateway/policies/{policy_id}/activate",
        headers=auth_headers(admin_context, idempotency_key="activate-policy-1"),
        json=body,
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["resource_id"] == second.json()["resource_id"]

    prompts = admin_context.client.get(
        "/v1/admin/model-gateway/prompts",
        headers=auth_headers(admin_context),
    )
    assert prompts.status_code == 200
    prompt = prompts.json()["items"][0]
    assert "template" not in prompt
    assert prompt["sha256"]
