from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.artifacts import ArtifactManifest, ArtifactRecord
from src.vyu.config import RuntimeSettings
from src.vyu.connectors import DummyConnector, JsonlAuditSink, PubMedConnector, SearchRequest
from src.vyu.connectors.health import (
    ValidationStage,
    run_connector_health_check,
    validate_pubmed_connector_stage,
)
from src.vyu.evidence import (
    ExternalEvidenceGradingConnector,
    ExternalEvidenceGradingProviderConfig,
    build_external_grading_request_record,
    build_methodology_assessments_from_hits,
    build_methodology_run_record,
    default_methodology_ruleset,
)
from src.vyu.evaluation import (
    EvaluationRegistry,
    EvaluationRun,
    compare_workflows,
    export_deep_dive_trajectory,
    render_adoption_report,
)
from src.vyu.generation import (
    build_evidence_context,
    generate_grounded_answer,
    validate_citations,
)
from src.vyu.governance import (
    ExternalGovernanceConnector,
    ExternalGovernanceProviderConfig,
    build_external_governance_request_record,
    build_governance_box,
    build_production_governance_box_record,
    build_production_trust_score_record,
    calculate_trust_score,
    default_trust_score_policy,
    export_audit_record,
)
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus
from src.vyu.memory import FollowUpDecision, ProductionResearchMemoryRecord
from src.vyu.review import create_review_task
from src.vyu.reports import (
    render_evidence_brief,
    render_policy_output,
    render_research_report,
)
from src.vyu.retrieval import (
    BM25Retriever,
    DenseKeywordRetriever,
    EvidenceObjectKind,
    EvidenceObjectRecord,
    ProductionHybridRetrievalService,
    RetrievalHit,
    RetrievalIndexKind,
    RetrievalIndexRecord,
    RetrievalQuery,
    evaluate_golden_questions,
)
from src.vyu.sources import SourceRegistry
from src.vyu.storage import ProductionAuditEvent, ProductionScope, ProductionStorage
from src.vyu.workflow import DeepDiveResult, run_guided_deep_dive


DEFAULT_QUESTION = "Does VX-101 reduce migraine days?"
DEEP_DIVE_QUESTION = (
    "Does VX-101 reduce migraine days in adults with episodic migraine compared with standard therapy?"
)
ARTIFACT_SOURCE_IDS = ["dummy_corpus", "golden_questions"]
ARTIFACT_GENERATION_USE = "artifact_generation"


def run_phase_outputs(
    root: Path = Path("."),
    output_dir: Path = Path("outputs"),
    source_registry_path: Path | None = None,
    sqlite_path: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    output_dir = output_dir.resolve()
    settings = RuntimeSettings.from_environment()
    approved_sources = _approved_manifest_sources(source_registry_path)
    generate_phase1_corpus(root)
    output_dir.mkdir(parents=True, exist_ok=True)

    corpus = load_dummy_corpus(root)
    retriever = BM25Retriever.from_corpus(corpus)
    dense_retriever = DenseKeywordRetriever.from_corpus(corpus)
    production_hybrid_retriever = ProductionHybridRetrievalService(
        lexical_retriever=retriever,
        semantic_retriever=dense_retriever,
        index_versions=("hybrid-local-v1",),
        retriever_versions={
            "bm25": "local-bm25-v1",
            "dense_keyword": "local-semantic-placeholder-v1",
            "rrf": "local-rrf-v1",
        },
    )
    artifacts: list[str] = []

    phase2_dir = output_dir / "phase2"
    phase2_dir.mkdir(parents=True, exist_ok=True)
    connector_audit_path = phase2_dir / "connector_audit.jsonl"
    if connector_audit_path.exists():
        connector_audit_path.unlink()
    connector = DummyConnector(corpus, audit_sink=JsonlAuditSink(connector_audit_path))
    connector_result = connector.search(SearchRequest(query="retracted", limit=3))
    fetched_document = connector.fetch(connector_result.documents[0].document_id)
    artifacts.append(
        _write_json(
            output_dir,
            phase2_dir / "connector_search_result.json",
            {
                "source": connector_result.source,
                "request": asdict(connector_result.request),
                "document_count": connector_result.document_count,
                "documents": [_document_to_json(document) for document in connector_result.documents],
                "passages": [_passage_to_json(passage) for passage in connector_result.passages],
                "fetched_document": _document_to_json(fetched_document),
            },
        )
    )
    artifacts.append(_relative(output_dir, connector_audit_path))

    phase3_dir = output_dir / "phase3"
    hits = retriever.search(RetrievalQuery(text=DEFAULT_QUESTION, top_k=10))
    retrieval_metrics = evaluate_golden_questions(corpus, retriever, top_k=10)
    production_hits, production_retrieval_run = production_hybrid_retriever.search_with_record(
        query=RetrievalQuery(text=DEFAULT_QUESTION, top_k=10),
        retrieval_run_id="retrieval-local-phase-output-run",
        run_id="local-phase-output-run",
        tenant_id="local_tenant",
        workspace_id="local_workspace",
        user_id="local_user",
        topic="vx101-migraine",
        created_at="2026-06-28T00:00:00Z",
        evaluation_suite="retrieval_baseline",
    )
    production_index_record = RetrievalIndexRecord(
        index_version="hybrid-local-v1",
        tenant_id="local_tenant",
        workspace_id="local_workspace",
        index_kind=RetrievalIndexKind.HYBRID,
        corpus_version="synthetic-vx101-v1",
        source_ids=("dummy_corpus", "golden_questions"),
        object_uri="s3://vyu-index-placeholder/local_tenant/local_workspace/hybrid-local-v1/",
        checksum_sha256=_stable_json_sha256(production_retrieval_run.to_json()),
        document_count=len(corpus.documents),
        passage_count=len(corpus.passages),
        created_at="2026-06-28T00:00:00Z",
        embedding_model="deterministic-dense-keyword-placeholder-v1",
        lexical_config={"backend": "bm25", "version": "local-bm25-v1"},
        semantic_config={"backend": "pgvector_placeholder", "version": "local-semantic-placeholder-v1"},
        metadata={"runtime": "production_control_plane_local"},
    )
    production_evidence_object = EvidenceObjectRecord(
        object_id="evidence-pack-local-phase-output-run",
        tenant_id="local_tenant",
        workspace_id="local_workspace",
        object_uri="s3://vyu-evidence-placeholder/local_tenant/local_workspace/evidence-pack-local-phase-output-run.jsonl",
        object_kind=EvidenceObjectKind.EVIDENCE_PACK,
        content_type="application/jsonl",
        checksum_sha256=_file_sha256(root / "data" / "dummy_articles" / "documents.jsonl"),
        size_bytes=(root / "data" / "dummy_articles" / "documents.jsonl").stat().st_size,
        source_id="dummy_corpus",
        evidence_pack_id="synthetic-vx101-v1",
        created_at="2026-06-28T00:00:00Z",
        metadata={"storage_backend": "s3_placeholder", "phi_ephi": "blocked"},
    )
    production_memory_record = ProductionResearchMemoryRecord(
        memory_id="memory-local-phase-output-run",
        run_id="local-phase-output-run",
        tenant_id="local_tenant",
        workspace_id="local_workspace",
        user_id="local_user",
        topic="vx101-migraine",
        question=DEFAULT_QUESTION,
        generated_search_queries=(DEFAULT_QUESTION,),
        retrieved_document_ids=production_retrieval_run.retrieved_document_ids,
        included_document_ids=tuple(hit.document_id for hit in production_hits[:5]),
        excluded_documents=tuple(
            {"document_id": document_id, "reason": "retracted"}
            for document_id in sorted(corpus.retracted_document_ids)
        ),
        generated_report_ids=("phase6/research_report.md", "phase6/evidence_brief.md"),
        model_versions={"semantic_retriever": "deterministic-dense-keyword-placeholder-v1"},
        policy_versions={"retrieval_policy": "retrieval_policy_v1"},
        follow_up_decision=FollowUpDecision.SEARCH_NEW_EVIDENCE,
        source_permissions=("dummy_corpus", "golden_questions"),
        access_labels=("public_synthetic",),
        retention_policy_id="pilot_research_memory_90d",
        retrieval_run_id=production_retrieval_run.retrieval_run_id,
        created_at="2026-06-28T00:00:00Z",
    )
    artifacts.append(
        _write_json(
            output_dir,
            phase3_dir / "production_retrieval_run.json",
            production_retrieval_run.to_json(),
        )
    )
    artifacts.append(
        _write_json(
            output_dir,
            phase3_dir / "retrieval_index_manifest.json",
            production_index_record.to_json(),
        )
    )
    artifacts.append(
        _write_json(
            output_dir,
            phase3_dir / "evidence_object_manifest.json",
            production_evidence_object.to_json(),
        )
    )
    artifacts.append(
        _write_json(
            output_dir,
            phase3_dir / "production_research_memory.json",
            production_memory_record.to_json(),
        )
    )
    artifacts.append(
        _write_json(
            output_dir,
            phase3_dir / "retrieval_hits.json",
            {
                "question": DEFAULT_QUESTION,
                "top_k": 10,
                "hits": [_hit_to_json(hit) for hit in hits],
            },
        )
    )
    artifacts.append(
        _write_json(
            output_dir,
            phase3_dir / "retrieval_metrics.json",
            retrieval_metrics,
        )
    )

    phase4_dir = output_dir / "phase4"
    context = build_evidence_context(DEFAULT_QUESTION, hits[:5])
    answer = generate_grounded_answer(context)
    validation = validate_citations(answer, context)
    artifacts.append(
        _write_json(output_dir, phase4_dir / "evidence_context.json", _context_to_json(context))
    )
    artifacts.append(_write_json(output_dir, phase4_dir / "grounded_answer.json", asdict(answer)))
    artifacts.append(
        _write_json(output_dir, phase4_dir / "citation_validation.json", asdict(validation))
    )

    phase5_dir = output_dir / "phase5"
    trust_score = calculate_trust_score(answer, context, validation)
    governance_box = build_governance_box(
        question=context.question,
        context=context,
        trust_score=trust_score,
        sources_searched=["dummy_corpus"],
    )
    artifacts.append(
        _write_json(
            output_dir,
            phase5_dir / "governance_audit_record.json",
            export_audit_record(answer, context, trust_score, governance_box),
        )
    )
    methodology_ruleset = default_methodology_ruleset(
        "migraine_neurology",
        created_at="2026-06-28T00:00:00Z",
    )
    methodology_assessments = build_methodology_assessments_from_hits(
        corpus=corpus,
        hits=production_hits[:5],
        retrieval_run=production_retrieval_run,
        ruleset=methodology_ruleset,
        specialty="migraine_neurology",
        created_at="2026-06-28T00:00:00Z",
    )
    methodology_run = build_methodology_run_record(
        methodology_run_id="methodology-local-phase-output-run",
        retrieval_run=production_retrieval_run,
        assessments=methodology_assessments,
        ruleset=methodology_ruleset,
        created_at="2026-06-28T00:00:00Z",
    )
    external_grading_provider = ExternalEvidenceGradingProviderConfig(
        provider_id="external_evidence_grading_api_placeholder",
        endpoint_url="https://evidence-grading.example.invalid/v1/grade",
        webhook_url="https://api.vyu.example.invalid/webhooks/evidence-grading",
        auth_secret_ref="aws-secretsmanager:vyu/external-evidence-grading/api-token",
        webhook_secret_ref="aws-secretsmanager:vyu/external-evidence-grading/webhook-secret",
        supported_specialties=("migraine_neurology", "general_biomedical_research"),
    )
    external_grading_request = build_external_grading_request_record(
        request_id="external-grading-local-phase-output-run",
        retrieval_run=production_retrieval_run,
        corpus=corpus,
        document_ids=tuple(assessment.document_id for assessment in methodology_assessments),
        ruleset=methodology_ruleset,
        provider_config=external_grading_provider,
        created_at="2026-06-28T00:00:00Z",
    )
    external_grading_request, external_grading_response = ExternalEvidenceGradingConnector(
        external_grading_provider,
        _ExternalGradingReplayTransport(),
    ).submit(
        external_grading_request,
        sent_at="2026-06-28T00:00:00Z",
    )
    artifacts.append(
        _write_json(
            output_dir,
            phase5_dir / "evidence_methodology_assessments.json",
            {
                "ruleset": methodology_ruleset.to_json(),
                "assessments": [assessment.to_json() for assessment in methodology_assessments],
            },
        )
    )
    artifacts.append(
        _write_json(
            output_dir,
            phase5_dir / "evidence_methodology_run.json",
            methodology_run.to_json(),
        )
    )
    artifacts.append(
        _write_json(
            output_dir,
            phase5_dir / "external_evidence_grading_request.json",
            external_grading_request.to_json(),
        )
    )
    if external_grading_response is not None:
        artifacts.append(
            _write_json(
                output_dir,
                phase5_dir / "external_evidence_grading_response.json",
                external_grading_response.to_json(),
            )
        )

    trust_score_policy = default_trust_score_policy(created_at="2026-06-28T00:00:00Z")
    production_trust_score_record = build_production_trust_score_record(
        trust_score_id="trust-score-local-phase-output-run",
        answer=answer,
        context=context,
        validation=validation,
        retrieval_run=production_retrieval_run,
        methodology_run=methodology_run,
        assessments=methodology_assessments,
        policy=trust_score_policy,
        created_at="2026-06-28T00:00:00Z",
    )
    production_governance_box_record = build_production_governance_box_record(
        governance_box_id="governance-box-local-phase-output-run",
        answer=answer,
        context=context,
        retrieval_run=production_retrieval_run,
        trust_score_record=production_trust_score_record,
        methodology_run=methodology_run,
        assessments=methodology_assessments,
        sources_searched=("dummy_corpus",),
        output_type="answer",
        audit_id="audit-local-phase-output-run",
        created_at="2026-06-28T00:00:00Z",
    )
    external_governance_provider = ExternalGovernanceProviderConfig(
        provider_id="external_governance_system_placeholder",
        endpoint_url="https://governance.example.invalid/v1/evaluate-output",
        webhook_url="https://api.vyu.example.invalid/webhooks/governance",
        auth_secret_ref="aws-secretsmanager:vyu/external-governance/api-token",
        webhook_secret_ref="aws-secretsmanager:vyu/external-governance/webhook-secret",
        include_passage_text=False,
    )
    external_governance_request = build_external_governance_request_record(
        request_id="external-governance-local-phase-output-run",
        answer=answer,
        context=context,
        retrieval_run=production_retrieval_run,
        trust_score=production_trust_score_record,
        governance_box=production_governance_box_record,
        methodology_run=methodology_run,
        assessments=methodology_assessments,
        provider_config=external_governance_provider,
        created_at="2026-06-28T00:00:00Z",
    )
    external_governance_request, external_governance_response = ExternalGovernanceConnector(
        external_governance_provider,
        _ExternalGovernanceReplayTransport(),
    ).submit(
        external_governance_request,
        sent_at="2026-06-28T00:00:00Z",
    )
    artifacts.append(
        _write_json(
            output_dir,
            phase5_dir / "production_trust_score_record.json",
            production_trust_score_record.to_json(),
        )
    )
    artifacts.append(
        _write_json(
            output_dir,
            phase5_dir / "production_governance_box_record.json",
            production_governance_box_record.to_json(),
        )
    )
    artifacts.append(
        _write_json(
            output_dir,
            phase5_dir / "external_governance_request.json",
            external_governance_request.to_json(),
        )
    )
    if external_governance_response is not None:
        artifacts.append(
            _write_json(
                output_dir,
                phase5_dir / "external_governance_response.json",
                external_governance_response.to_json(),
            )
        )

    phase6_dir = output_dir / "phase6"
    deep_dive = run_guided_deep_dive(DEEP_DIVE_QUESTION, retriever, max_rounds=2)
    artifacts.append(
        _write_json(output_dir, phase6_dir / "deep_dive_result.json", _deep_dive_to_json(deep_dive))
    )
    artifacts.append(
        _write_text(
            output_dir,
            phase6_dir / "evidence_brief.md",
            render_evidence_brief(answer, trust_score, governance_box),
        )
    )
    artifacts.append(
        _write_text(
            output_dir,
            phase6_dir / "research_report.md",
            render_research_report(answer, context, trust_score, governance_box),
        )
    )
    artifacts.append(
        _write_text(
            output_dir,
            phase6_dir / "policy_output.md",
            render_policy_output(answer, trust_score, governance_box),
        )
    )

    phase7_dir = output_dir / "phase7"
    trajectory = export_deep_dive_trajectory(deep_dive)
    comparison = compare_workflows(
        corpus,
        retriever,
        questions=[DEFAULT_QUESTION, DEEP_DIVE_QUESTION],
    )
    artifacts.append(
        _write_json(output_dir, phase7_dir / "research_trajectory.json", trajectory.to_json())
    )
    artifacts.append(
        _write_json(output_dir, phase7_dir / "workflow_comparison.json", comparison.to_json())
    )
    artifacts.append(
        _write_text(
            output_dir,
            phase7_dir / "adoption_report.md",
            render_adoption_report(comparison),
        )
    )

    registry_path = output_dir / "evaluation" / "runs.jsonl"
    if registry_path.exists():
        registry_path.unlink()
    evaluation_run = EvaluationRun(
        run_id="local-phase-output-run",
        suite="retrieval_baseline",
        subject="bm25",
        metrics={
            key: float(value)
            for key, value in retrieval_metrics.items()
            if isinstance(value, (int, float))
        },
        dataset_version="golden-questions-v1",
        artifact_manifest_path="outputs/artifact_manifest.json",
    )
    EvaluationRegistry(registry_path).append(evaluation_run)
    artifacts.append(_relative(output_dir, registry_path))

    artifact_records = [
        _artifact_record(output_dir, relative_path)
        for relative_path in artifacts
    ]
    artifact_manifest = ArtifactManifest(
        run_id="local-phase-output-run",
        environment=settings.environment,
        tenant_id="local_tenant",
        workspace_id="local_workspace",
        corpus_version="synthetic-vx101-v1",
        index_version="hybrid-local-v1",
        artifacts=artifact_records,
        sources=approved_sources,
    )
    artifact_manifest.write(output_dir / "artifact_manifest.json")
    artifacts.insert(0, "artifact_manifest.json")

    run_summary = {
        "run_id": artifact_manifest.run_id,
        "environment": artifact_manifest.environment,
        "tenant_id": artifact_manifest.tenant_id,
        "workspace_id": artifact_manifest.workspace_id,
        "corpus_version": artifact_manifest.corpus_version,
        "index_version": artifact_manifest.index_version,
        "artifact_count": len(artifact_manifest.artifacts),
        "source_count": len(artifact_manifest.sources),
        "evaluation_metric_names": sorted(evaluation_run.metrics),
        "artifact_manifest_path": "outputs/artifact_manifest.json",
        "evaluation_registry_path": "outputs/evaluation/runs.jsonl",
        "sqlite_path": str(sqlite_path) if sqlite_path is not None else None,
        "readiness_command": (
            "python scripts/check_production_readiness.py --sqlite-db outputs/production.sqlite "
            "--artifact-manifest outputs/artifact_manifest.json --run-summary outputs/run_summary.json "
            "--run-id local-phase-output-run "
            "--tenant-id local_tenant --workspace-id local_workspace"
        ),
    }
    _write_json(output_dir, output_dir / "run_summary.json", run_summary)
    artifacts.insert(1, "run_summary.json")

    if sqlite_path is not None:
        storage = ProductionStorage(sqlite_path.resolve())
        storage.initialize()
        storage.save_artifact_manifest(artifact_manifest)
        storage.save_evaluation_run(evaluation_run)
        created_at = datetime.now(timezone.utc).isoformat()
        storage.append_audit_event(
            ProductionAuditEvent(
                event_id=_audit_event_id(artifact_manifest.run_id, "artifact_manifest_saved"),
                run_id=artifact_manifest.run_id,
                event_type="artifact_manifest_saved",
                payload={
                    "artifact_count": len(artifact_manifest.artifacts),
                    "source_count": len(artifact_manifest.sources),
                    "sqlite_path": str(sqlite_path),
                },
                created_at=created_at,
            )
        )
        storage.append_audit_event(
            ProductionAuditEvent(
                event_id=_audit_event_id(artifact_manifest.run_id, "evaluation_run_saved"),
                run_id=artifact_manifest.run_id,
                event_type="evaluation_run_saved",
                payload={
                    "suite": evaluation_run.suite,
                    "subject": evaluation_run.subject,
                    "metric_names": sorted(evaluation_run.metrics),
                },
                created_at=created_at,
            )
        )
        storage.append_audit_event(
            ProductionAuditEvent(
                event_id=_audit_event_id(artifact_manifest.run_id, "phase_outputs_completed"),
                run_id=artifact_manifest.run_id,
                event_type="phase_outputs_completed",
                payload={
                    "output_dir": str(output_dir),
                    "artifact_manifest_path": "outputs/artifact_manifest.json",
                },
                created_at=created_at,
            )
        )
        scope = ProductionScope(
            tenant_id=artifact_manifest.tenant_id,
            workspace_id=artifact_manifest.workspace_id,
        )
        storage.record_evidence_object(
            production_evidence_object,
            run_id=artifact_manifest.run_id,
            audit_event_id=_audit_event_id(
                artifact_manifest.run_id,
                "evidence_object_recorded",
            ),
            audit_created_at=created_at,
        )
        storage.record_retrieval_index(
            production_index_record,
            run_id=artifact_manifest.run_id,
            audit_event_id=_audit_event_id(
                artifact_manifest.run_id,
                "retrieval_index_recorded",
            ),
            audit_created_at=created_at,
        )
        storage.record_retrieval_run(
            production_retrieval_run,
            audit_event_id=_audit_event_id(
                artifact_manifest.run_id,
                "retrieval_run_recorded",
            ),
            audit_created_at=created_at,
        )
        storage.record_production_research_memory(
            production_memory_record,
            audit_event_id=_audit_event_id(
                artifact_manifest.run_id,
                "production_research_memory_saved",
            ),
            audit_created_at=created_at,
        )
        for assessment in methodology_assessments:
            storage.record_evidence_methodology_assessment(
                assessment,
                audit_event_id=_audit_event_id(
                    artifact_manifest.run_id,
                    f"evidence_methodology_assessment_{assessment.document_id}",
                ),
                audit_created_at=created_at,
            )
        storage.record_evidence_methodology_run(
            methodology_run,
            audit_event_id=_audit_event_id(
                artifact_manifest.run_id,
                "evidence_methodology_run_recorded",
            ),
            audit_created_at=created_at,
        )
        storage.record_external_evidence_grading_request(
            external_grading_request,
            audit_event_id=_audit_event_id(
                artifact_manifest.run_id,
                "external_evidence_grading_request_recorded",
            ),
            audit_created_at=created_at,
        )
        if external_grading_response is not None:
            storage.record_external_evidence_grading_response(
                external_grading_response,
                audit_event_id=_audit_event_id(
                    artifact_manifest.run_id,
                    "external_evidence_grading_response_recorded",
                ),
                audit_created_at=created_at,
            )
        storage.record_production_trust_score(
            production_trust_score_record,
            audit_event_id=_audit_event_id(
                artifact_manifest.run_id,
                "production_trust_score_recorded",
            ),
            audit_created_at=created_at,
        )
        storage.record_production_governance_box(
            production_governance_box_record,
            audit_event_id=_audit_event_id(
                artifact_manifest.run_id,
                "production_governance_box_recorded",
            ),
            audit_created_at=created_at,
        )
        storage.record_external_governance_request(
            external_governance_request,
            audit_event_id=_audit_event_id(
                artifact_manifest.run_id,
                "external_governance_request_recorded",
            ),
            audit_created_at=created_at,
        )
        if external_governance_response is not None:
            storage.record_external_governance_response(
                external_governance_response,
                audit_event_id=_audit_event_id(
                    artifact_manifest.run_id,
                    "external_governance_response_recorded",
                ),
                audit_created_at=created_at,
            )
        if governance_box.human_review_required:
            review_task = create_review_task(
                run_id=artifact_manifest.run_id,
                governance_box=governance_box,
                tenant_id=scope.tenant_id,
                workspace_id=scope.workspace_id,
                created_at=created_at,
            )
            storage.record_review_task(
                review_task,
                audit_event_id=_audit_event_id(
                    artifact_manifest.run_id,
                    "review_task_created",
                ),
                audit_created_at=created_at,
            )
        connector_health = run_connector_health_check(
            source_id="dummy_corpus",
            connector_name="DummyConnector",
            operation=lambda: {
                "document_count": connector_result.document_count,
                "fetched_document_id": fetched_document.document_id,
            },
            checked_at=created_at,
        )
        pubmed_validation = validate_pubmed_connector_stage(
            connector=PubMedConnector(transport=_pubmed_replay_transport),
            stage=ValidationStage.REPLAY,
            query="VX-101",
            limit=1,
            checked_at=created_at,
        )
        storage.record_connector_health(
            run_id=artifact_manifest.run_id,
            scope=scope,
            record=connector_health,
            audit_event_id=_audit_event_id(
                artifact_manifest.run_id,
                "connector_health_recorded",
            ),
            audit_created_at=created_at,
        )
        storage.record_staged_connector_validation(
            run_id=artifact_manifest.run_id,
            scope=scope,
            record=pubmed_validation,
            audit_event_id=_audit_event_id(
                artifact_manifest.run_id,
                "connector_validation_recorded",
            ),
            audit_created_at=created_at,
        )

    return {
        "root": str(root),
        "output_dir": str(output_dir),
        "question": DEFAULT_QUESTION,
        "deep_dive_question": DEEP_DIVE_QUESTION,
        "artifacts": artifacts,
    }


class _ExternalGradingReplayTransport:
    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, Any]:
        return {
            "status": "accepted",
            "external_job_id": "external-grading-job-placeholder",
            "provider_version": "external-evidence-grading-placeholder-v1",
            "received_document_count": len(payload.get("documents", [])),
            "request_id": headers.get("X-Vyu-Request-Id"),
            "endpoint_url": url,
            "timeout_seconds": timeout_seconds,
        }


class _ExternalGovernanceReplayTransport:
    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, Any]:
        governance_box = dict(payload.get("governance_box", {}))
        return {
            "status": "accepted",
            "external_job_id": "external-governance-job-placeholder",
            "provider_version": "external-governance-placeholder-v1",
            "decision_status": governance_box.get("decision_status", "review_required"),
            "export_status": governance_box.get("export_status", "pending_review"),
            "review_required": governance_box.get("human_review_required", True),
            "request_id": headers.get("X-Vyu-Request-Id"),
            "governance_box_id": headers.get("X-Vyu-Governance-Box-Id"),
            "endpoint_url": url,
            "timeout_seconds": timeout_seconds,
        }


def _write_json(output_dir: Path, path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return _relative(output_dir, path)


def _write_text(output_dir: Path, path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    return _relative(output_dir, path)


def _stable_json_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(output_dir: Path, path: Path) -> str:
    return path.relative_to(output_dir).as_posix()


def _artifact_record(output_dir: Path, relative_path: str) -> ArtifactRecord:
    path = output_dir / relative_path
    phase = relative_path.split("/", 1)[0]
    return ArtifactRecord(
        phase=phase,
        path=relative_path,
        artifact_type=path.stem,
        source_ids=ARTIFACT_SOURCE_IDS,
        checksum_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def _approved_manifest_sources(source_registry_path: Path | None) -> list[dict[str, Any]]:
    if source_registry_path is None:
        return []
    registry = SourceRegistry.read(source_registry_path)
    return [
        registry.require_approved(source_id, intended_use=ARTIFACT_GENERATION_USE).to_json()
        for source_id in ARTIFACT_SOURCE_IDS
    ]


def _audit_event_id(run_id: str, event_type: str) -> str:
    return f"{run_id}-{event_type}-{uuid.uuid4().hex}"


def _pubmed_replay_transport(_url: str, params: dict[str, object]) -> dict[str, Any]:
    mode = str(params["mode"])
    if mode == "search":
        return {"ids": ["12345"]}
    if mode == "summary":
        return {
            "documents": [
                {
                    "uid": "12345",
                    "title": "Replayed VX-101 PubMed validation record",
                    "pubdate": "2026 Jan",
                    "source": "Replay Journal",
                }
            ]
        }
    raise ValueError(f"Unsupported PubMed replay mode: {mode}")


def _document_to_json(document) -> dict[str, Any]:
    data = asdict(document)
    data["study_design"] = str(document.study_design)
    return data


def _passage_to_json(passage) -> dict[str, Any]:
    return asdict(passage)


def _hit_to_json(hit: RetrievalHit) -> dict[str, Any]:
    return {
        "document_id": hit.document_id,
        "passage_id": hit.passage_id,
        "document": _document_to_json(hit.document),
        "passage": _passage_to_json(hit.passage),
        "score": asdict(hit.score),
        "trace": asdict(hit.trace),
    }


def _context_to_json(context) -> dict[str, Any]:
    return {
        "question": context.question,
        "items": [asdict(item) for item in context.items],
    }


def _deep_dive_to_json(result: DeepDiveResult) -> dict[str, Any]:
    return {
        "question": result.question,
        "pico": asdict(result.pico),
        "rounds": [
            {
                "round_number": round_result.round_number,
                "query": round_result.query,
                "coverage_gap": round_result.coverage_gap,
                "hits": [_hit_to_json(hit) for hit in round_result.hits],
            }
            for round_result in result.rounds
        ],
        "stopping_reason": result.stopping_reason,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Persist Vyu Phase 2-7 output artifacts.")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--source-registry", type=Path, default=None)
    parser.add_argument("--sqlite-db", type=Path, default=None)
    args = parser.parse_args()

    manifest = run_phase_outputs(
        root=args.root,
        output_dir=args.output_dir,
        source_registry_path=args.source_registry,
        sqlite_path=args.sqlite_db,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
