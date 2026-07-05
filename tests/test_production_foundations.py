import tempfile
import time
import unittest
from pathlib import Path

from src.vyu.artifacts import ArtifactManifest, ArtifactRecord
from src.vyu.config import RuntimeSettings
from src.vyu.connectors.runtime import ConnectorRuntime, RetryPolicy, StaticRateLimiter
from src.vyu.evaluation.registry import EvaluationRegistry, EvaluationRun


class ProductionFoundationTests(unittest.TestCase):
    def test_runtime_settings_loads_environment_scoped_connector_defaults(self):
        settings = RuntimeSettings.from_mapping(
            {
                "VYU_ENV": "staging",
                "VYU_TENANT_MODE": "multi_tenant",
                "VYU_CONNECTOR_TIMEOUT_SECONDS": "8.5",
                "VYU_CONNECTOR_MAX_RETRIES": "4",
                "VYU_CONNECTOR_RATE_LIMIT_PER_MINUTE": "120",
                "VYU_ENABLE_LIVE_CONNECTORS": "true",
                "VYU_NCBI_TOOL": "vyu-staging",
                "VYU_NCBI_EMAIL": "ops@example.com",
                "VYU_NCBI_API_KEY": "secret-key",
            }
        )

        self.assertEqual("staging", settings.environment)
        self.assertEqual("multi_tenant", settings.tenant_mode)
        self.assertEqual(8.5, settings.connector_timeout_seconds)
        self.assertEqual(4, settings.connector_max_retries)
        self.assertEqual(120, settings.connector_rate_limit_per_minute)
        self.assertTrue(settings.enable_live_connectors)
        self.assertEqual("vyu-staging", settings.ncbi_tool)
        self.assertEqual("ops@example.com", settings.ncbi_email)
        self.assertEqual("secret-key", settings.ncbi_api_key)

    def test_connector_runtime_retries_transient_failures_and_tracks_attempts(self):
        attempts = 0

        def flaky_operation():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise TimeoutError("temporary connector timeout")
            return "ok"

        runtime = ConnectorRuntime(
            retry_policy=RetryPolicy(max_attempts=3, backoff_seconds=0),
            rate_limiter=StaticRateLimiter(max_calls=10, window_seconds=60),
            sleep=lambda _seconds: None,
        )

        result = runtime.run("pubmed", "search", flaky_operation)

        self.assertEqual("ok", result.value)
        self.assertEqual(3, result.attempts)
        self.assertEqual("ok", result.status)
        self.assertEqual(3, attempts)

    def test_connector_runtime_rate_limiter_blocks_excess_calls(self):
        limiter = StaticRateLimiter(max_calls=1, window_seconds=60, clock=time.monotonic)
        runtime = ConnectorRuntime(
            retry_policy=RetryPolicy(max_attempts=1, backoff_seconds=0),
            rate_limiter=limiter,
        )

        runtime.run("pubmed", "search", lambda: "first")

        with self.assertRaises(RuntimeError):
            runtime.run("pubmed", "search", lambda: "second")

    def test_artifact_manifest_round_trips_with_source_and_index_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            manifest = ArtifactManifest(
                run_id="run-001",
                environment="staging",
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                corpus_version="corpus-2026-06-13",
                index_version="bm25-001",
                artifacts=[
                    ArtifactRecord(
                        phase="phase4",
                        path="phase4/grounded_answer.json",
                        artifact_type="grounded_answer",
                        source_ids=["dummy_corpus"],
                        checksum_sha256="abc123",
                    )
                ],
            )

            manifest.write(path)
            loaded = ArtifactManifest.read(path)

        self.assertEqual(manifest.to_json(), loaded.to_json())
        self.assertEqual("phase4/grounded_answer.json", loaded.artifacts[0].path)

    def test_evaluation_registry_appends_jsonl_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = EvaluationRegistry(Path(tmp) / "runs.jsonl")
            run = EvaluationRun(
                run_id="eval-001",
                suite="retrieval_baseline",
                subject="bm25",
                metrics={"recall_at_10": 0.72},
                dataset_version="golden-questions-v1",
                artifact_manifest_path="outputs/artifact_manifest.json",
            )

            registry.append(run)
            loaded = registry.read_all()

        self.assertEqual([run.to_json()], [item.to_json() for item in loaded])

    def test_required_production_docs_exist_with_decision_sections(self):
        required = {
            "docs/production/intended-use.md": "Forbidden Uses",
            "docs/production/forbidden-uses.md": "Export and Release Blocks",
            "docs/production/product-claim-inventory.md": "Allowed Claims",
            "docs/production/regulatory-position.md": "Initial Position",
            "docs/production/regulatory-review-checklist.md": "Review Checklist",
            "docs/production/access-control-matrix.md": "Role Permission Matrix",
            "docs/production/human-review-workflow.md": "Export Gate",
            "docs/production/reviewer-queue-api.md": "Route Contracts",
            "docs/production/reviewer-queue-route-runtime.md": "Route Runtime",
            "docs/production/report-export-route-runtime.md": "Report Export Route Runtime",
            "docs/production/service-route-runtime.md": "Service Route Runtime",
            "docs/production/identity-mapping.md": "Claim Mapping Contract",
            "docs/production/deployment-http-adapter.md": "Deployment HTTP Adapter",
            "docs/production/api-service-shell.md": "API Service Shell",
            "docs/production/serverless-handler.md": "Serverless Handler",
            "docs/production/deployment-composition.md": "Deployment Composition",
            "docs/production/deployment-smoke-test.md": "Smoke Test Contract",
            "docs/production/deployment-operator-config.md": "Operator Config Contract",
            "docs/production/deployment-app-entrypoint.md": "App Entrypoint Contract",
            "docs/production/deployment-package-manifest.md": "Package Manifest Contract",
            "docs/production/deployment-package-plan.md": "Package Plan Contract",
            "docs/production/deployment-package-archive.md": "Archive Builder Contract",
            "docs/production/deployment-package-evidence.md": "Evidence Contract",
            "docs/production/deployment-release-package-checklist.md": "Checklist Contract",
            "docs/production/deployment-command-transcript.md": "Transcript Contract",
            "docs/production/deployment-transcript-bundle.md": "Bundle Contract",
            "docs/production/deployment-release-evidence-summary.md": "Release Evidence Summary Contract",
            "docs/production/deployment-release-review-gate.md": "Release Review Gate Contract",
            "docs/production/deployment-release-handoff-bundle.md": "Release Handoff Bundle Contract",
            "docs/production/deployment-release-handoff-archive.md": "Release Handoff Archive Contract",
            "docs/production/deployment-release-channel-preparation.md": "Release Channel Preparation Contract",
            "docs/production/deployment-release-channel-acceptance.md": "Release Channel Acceptance Contract",
            "docs/production/deployment-release-channel-publication.md": "Release Channel Publication Contract",
            "docs/production/deployment-release-channel-evidence-index.md": "Release Channel Evidence Index Contract",
            "docs/production/deployment-release-channel-export-summary.md": "Evidence Export Summary Contract",
            "docs/production/deployment-release-channel-target-readiness.md": "Target Readiness Contract",
            "docs/production/deployment-release-channel-target-decision.md": "Target Decision Contract",
            "docs/production/deployment-release-channel-provider-preflight.md": "Release-Channel Provider-Planning Preflight Contract",
            "docs/production/deployment-release-channel-provider-decision.md": "Release-Channel Provider-Planning Decision Record Contract",
            "docs/production/connector-health-validation.md": "Staged Validation",
            "docs/production/compliance-evidence-bundle.md": "Bundle Contents",
            "docs/production/compliance-attestations.md": "Attestation Command",
            "docs/production/pilot-release-decision.md": "Release Decision Command",
            "docs/production/privacy-data-flow.md": "PHI/ePHI Gate",
            "docs/production/model-safety-policy.md": "Prompt-Injection Policy",
            "docs/production/report-export-policy.md": "Report Export Gate",
            "docs/production/source-registry-schema.md": "Required Fields",
            "docs/production/security-architecture.md": "Security Controls",
            "docs/production/threat-model.md": "Threats",
        }

        for path, required_heading in required.items():
            doc_path = Path(path)
            self.assertTrue(doc_path.exists(), path)
            text = doc_path.read_text(encoding="utf-8")
            self.assertIn(required_heading, text, path)

    def test_production_threat_model_reflects_implemented_foundation_controls(self):
        text = Path("docs/production/threat-model.md").read_text(encoding="utf-8")

        required_controls = [
            "PubMed HTTP and replay transports",
            "source approval gate",
            "SQLite production audit event storage",
            "tenant/workspace scoped storage reads",
        ]
        stale_risks = [
            "Live connectors are not yet implemented.",
            "Persistent audit/event store is not yet implemented.",
        ]

        for control in required_controls:
            self.assertIn(control, text)
        for risk in stale_risks:
            self.assertNotIn(risk, text)

    def test_production_overview_tracks_authorization_foundation(self):
        overview = Path("docs/project-overview-and-usage.md").read_text(encoding="utf-8")
        migration = Path("docs/production-grade-migration-plan.md").read_text(encoding="utf-8")

        required_snippets = [
            "Tenant/workspace authorization policy in `src/vyu/authz/`.",
            "| Authorization foundation | `src/vyu/authz/` | Tenant/workspace role rules for production-shaped access checks |",
            "`docs/production/access-control-matrix.md`",
        ]

        self.assertIn(required_snippets[0], overview)
        self.assertIn(required_snippets[1], migration)
        self.assertIn(required_snippets[2], overview)

    def test_production_overview_tracks_human_review_foundation(self):
        overview = Path("docs/project-overview-and-usage.md").read_text(encoding="utf-8")
        migration = Path("docs/production-grade-migration-plan.md").read_text(encoding="utf-8")

        required_snippets = [
            "Human review task and export-gating policy in `src/vyu/review/`.",
            "Persisted reviewer queue service boundaries in `src/vyu/review/queue.py`.",
            "Framework-neutral reviewer queue API and worker adapters in `src/vyu/entrypoints/review_queue.py`.",
            "Framework-neutral reviewer queue route runtime in `src/vyu/entrypoints/review_queue_routes.py`.",
            "Framework-neutral report-export route runtime in `src/vyu/entrypoints/report_export_routes.py`.",
            "Framework-neutral service route runtime in `src/vyu/entrypoints/service_routes.py`.",
            "Authentication identity mapping in `src/vyu/authn/`.",
            "Deployment HTTP adapter in `src/vyu/deployment/http_adapter.py`.",
            "Reviewer queue inspection command in `scripts/inspect_review_queue.py`.",
            "Reviewer decision recording command in `scripts/record_review_decision.py`.",
            "When the generated governance box requires human review, SQLite persistence also creates a pending review task and `review_task_created` audit event for the run.",
            "| Human review foundation | `src/vyu/review/` | Review tasks, reviewer decisions, and export gate decisions |",
            "| Reviewer queue service | `src/vyu/review/queue.py` | Loads scoped persisted review queues, filters by status, and records authorized reviewer decisions |",
            "| Reviewer queue entry adapters | `src/vyu/entrypoints/review_queue.py` | Framework-neutral API and worker adapters for queue listing and reviewer decisions |",
            "| Reviewer queue route runtime | `src/vyu/entrypoints/review_queue_routes.py` | Framework-neutral HTTP-shaped route runtime for reviewer queue list and decision routes |",
            "| Report export route runtime | `src/vyu/entrypoints/report_export_routes.py` | Framework-neutral HTTP-shaped route runtime for report export requests and local phase-output artifact loading |",
            "| Service route runtime | `src/vyu/entrypoints/service_routes.py` | Framework-neutral top-level route runtime for request IDs, audit correlation, identity headers, health checks, envelopes, and route dispatch |",
            "| Authentication identity mapping | `src/vyu/authn/` | Maps trusted deployed identity claims into Vyu user, tenant, workspace, and role headers without choosing an auth provider or web framework |",
            "| Deployment HTTP adapter | `src/vyu/deployment/http_adapter.py` | Validates HS256 bearer JWTs, preserves request/audit IDs, passes trusted claims into the service runtime, and fails closed before dispatch |",
            "| Reviewer queue operator inspection | `scripts/inspect_review_queue.py` | Authorized CLI inspection of scoped review queues using the same entry adapter as deployed routes |",
            "| Reviewer decision operator command | `scripts/record_review_decision.py` | Authorized CLI approve/reject decisions using the same decision adapter as deployed routes |",
            "| Review persistence | `src/vyu/storage/production.py` | SQLite review task storage, review decision audit events, and backup/restore support |",
            "| Phase-output review task creation | `scripts/run_phase_outputs.py --sqlite-db ...` | Creates pending scoped review tasks and `review_task_created` audit events when governance requires human review |",
            "| Operator inspection | `scripts/inspect_production_store.py` | Scoped JSON export for manifests, evaluation runs, review tasks, review decisions, connector health, staged validation, privacy approvals, readiness results, and audit events |",
            "`docs/production/human-review-workflow.md`",
            "`docs/production/reviewer-queue-api.md`",
            "`docs/production/reviewer-queue-route-runtime.md`",
            "`docs/production/report-export-route-runtime.md`",
            "`docs/production/service-route-runtime.md`",
            "`docs/production/identity-mapping.md`",
            "`docs/production/deployment-http-adapter.md`",
            "final report-export decision audit events",
        ]

        for snippet in required_snippets[:11]:
            self.assertIn(snippet, overview)
        for snippet in required_snippets[11:24]:
            self.assertIn(snippet, migration)
        for snippet in required_snippets[24:31]:
            self.assertIn(snippet, overview)
        self.assertIn(required_snippets[31], migration)

    def test_production_overview_tracks_deployment_release_evidence_chain(self):
        overview = Path("docs/project-overview-and-usage.md").read_text(encoding="utf-8")
        migration = Path("docs/production-grade-migration-plan.md").read_text(encoding="utf-8")
        production_readme = Path("docs/production/README.md").read_text(encoding="utf-8")
        combined = "\n".join([overview, migration, production_readme])

        required_snippets = [
            "Deployment smoke-test and operator-config validation in `src/vyu/deployment/smoke.py`",
            "Deployment app entrypoint and packaging metadata in `apps/serverless/handler.py`",
            "Deterministic deployment package plan/archive/evidence tooling in `src/vyu/deployment/package_plan.py`",
            "Deployment release checklist, transcript bundle, evidence summary, review gate, and handoff bundle tooling",
            "| Deployment package evidence | `src/vyu/deployment/package_evidence.py` and `scripts/write_deployment_package_evidence.py` |",
            "| Deployment release handoff bundle | `src/vyu/deployment/release_handoff.py` and `scripts/build_deployment_release_handoff.py` |",
            "Deployment release handoff bundle: `docs/production/deployment-release-handoff-bundle.md`",
        ]

        for snippet in required_snippets:
            self.assertIn(snippet, combined)

    def test_production_overview_tracks_deployment_release_handoff_archive(self):
        overview = Path("docs/project-overview-and-usage.md").read_text(encoding="utf-8")
        migration = Path("docs/production-grade-migration-plan.md").read_text(encoding="utf-8")
        production = Path("docs/production/README.md").read_text(encoding="utf-8")
        archive_doc = Path("docs/production/deployment-release-handoff-archive.md").read_text(encoding="utf-8")
        runbook = Path("docs/production/operator-runbook.md").read_text(encoding="utf-8")

        required_snippets = [
            "Deployment release handoff archive/inventory in `src/vyu/deployment/release_handoff_archive.py` and `scripts/build_deployment_release_handoff_archive.py`.",
            "| Deployment release handoff archive | `src/vyu/deployment/release_handoff_archive.py` and `scripts/build_deployment_release_handoff_archive.py` | Deterministic local handoff evidence inventory",
            "Deployment release handoff archive: `docs/production/deployment-release-handoff-archive.md`",
            "src/vyu/deployment/release_handoff_archive.py",
            "scripts/build_deployment_release_handoff_archive.py",
            "recorded_hashes_match_files",
            "archive_entry_hashes_match_inventory",
            "local release-channel preparation",
            "python scripts/build_deployment_release_handoff_archive.py --handoff outputs/deployment_release_handoff.json --created-at 2026-06-15T03:15:00Z --inventory outputs/deployment_release_handoff_inventory.json --archive outputs/deployment_release_handoff.zip",
        ]

        self.assertIn(required_snippets[0], overview)
        self.assertIn(required_snippets[1], migration)
        self.assertIn(required_snippets[2], production)
        self.assertIn(required_snippets[3], archive_doc)
        self.assertIn(required_snippets[4], archive_doc)
        self.assertIn(required_snippets[5], archive_doc)
        self.assertIn(required_snippets[6], archive_doc)
        self.assertIn(required_snippets[7], production)
        self.assertIn(required_snippets[8], runbook)

    def test_production_overview_tracks_deployment_release_channel_preparation(self):
        overview = Path("docs/project-overview-and-usage.md").read_text(encoding="utf-8")
        migration = Path("docs/production-grade-migration-plan.md").read_text(encoding="utf-8")
        production = Path("docs/production/README.md").read_text(encoding="utf-8")
        channel_doc = Path("docs/production/deployment-release-channel-preparation.md").read_text(encoding="utf-8")
        runbook = Path("docs/production/operator-runbook.md").read_text(encoding="utf-8")

        required_snippets = [
            "Deployment release-channel preparation in `src/vyu/deployment/release_channel.py` and `scripts/prepare_deployment_release_channel.py`.",
            "| Deployment release-channel preparation | `src/vyu/deployment/release_channel.py` and `scripts/prepare_deployment_release_channel.py` | Local release-channel provenance manifest",
            "Deployment release-channel preparation: `docs/production/deployment-release-channel-preparation.md`",
            "src/vyu/deployment/release_channel.py",
            "scripts/prepare_deployment_release_channel.py",
            "archive_hash_matches_inventory",
            "inventory_artifact_hashes_match",
            "local release-channel acceptance record",
            "python scripts/prepare_deployment_release_channel.py --inventory outputs/deployment_release_handoff_inventory.json --archive outputs/deployment_release_handoff.zip --created-at 2026-06-15T03:30:00Z --channel local-release-channel --output outputs/deployment_release_channel_preparation.json",
        ]

        self.assertIn(required_snippets[0], overview)
        self.assertIn(required_snippets[1], migration)
        self.assertIn(required_snippets[2], production)
        self.assertIn(required_snippets[3], channel_doc)
        self.assertIn(required_snippets[4], channel_doc)
        self.assertIn(required_snippets[5], channel_doc)
        self.assertIn(required_snippets[6], channel_doc)
        self.assertIn(required_snippets[7], production)
        self.assertIn(required_snippets[8], runbook)

    def test_production_overview_tracks_deployment_release_channel_acceptance(self):
        overview = Path("docs/project-overview-and-usage.md").read_text(encoding="utf-8")
        migration = Path("docs/production-grade-migration-plan.md").read_text(encoding="utf-8")
        production = Path("docs/production/README.md").read_text(encoding="utf-8")
        acceptance_doc = Path("docs/production/deployment-release-channel-acceptance.md").read_text(encoding="utf-8")
        runbook = Path("docs/production/operator-runbook.md").read_text(encoding="utf-8")

        required_snippets = [
            "Deployment release-channel acceptance in `src/vyu/deployment/release_channel_acceptance.py` and `scripts/accept_deployment_release_channel.py`.",
            "| Deployment release-channel acceptance | `src/vyu/deployment/release_channel_acceptance.py` and `scripts/accept_deployment_release_channel.py` | Local operator approve/block record",
            "Deployment release-channel acceptance: `docs/production/deployment-release-channel-acceptance.md`",
            "src/vyu/deployment/release_channel_acceptance.py",
            "scripts/accept_deployment_release_channel.py",
            "preparation_archive_hash_bound",
            "approve_requires_ready_preparation",
            "local release-channel publication manifest",
            "python scripts/accept_deployment_release_channel.py --preparation outputs/deployment_release_channel_preparation.json --decision approve --operator-id release-operator --operator-role deployment_operator --comment \"Release channel preparation accepted for local publication.\" --decided-at 2026-06-15T03:45:00Z --output outputs/deployment_release_channel_acceptance.json",
        ]

        self.assertIn(required_snippets[0], overview)
        self.assertIn(required_snippets[1], migration)
        self.assertIn(required_snippets[2], production)
        self.assertIn(required_snippets[3], acceptance_doc)
        self.assertIn(required_snippets[4], acceptance_doc)
        self.assertIn(required_snippets[5], acceptance_doc)
        self.assertIn(required_snippets[6], acceptance_doc)
        self.assertIn(required_snippets[7], production)
        self.assertIn(required_snippets[8], runbook)

    def test_production_overview_tracks_deployment_release_channel_publication_manifest(self):
        overview = Path("docs/project-overview-and-usage.md").read_text(encoding="utf-8")
        migration = Path("docs/production-grade-migration-plan.md").read_text(encoding="utf-8")
        production = Path("docs/production/README.md").read_text(encoding="utf-8")
        publication_doc = Path("docs/production/deployment-release-channel-publication.md").read_text(encoding="utf-8")
        runbook = Path("docs/production/operator-runbook.md").read_text(encoding="utf-8")

        required_snippets = [
            "Deployment release-channel publication manifest in `src/vyu/deployment/release_channel_publication.py` and `scripts/prepare_deployment_release_channel_publication.py`.",
            "| Deployment release-channel publication manifest | `src/vyu/deployment/release_channel_publication.py` and `scripts/prepare_deployment_release_channel_publication.py` | Local no-op publication-readiness manifest",
            "Deployment release-channel publication manifest: `docs/production/deployment-release-channel-publication.md`",
            "src/vyu/deployment/release_channel_publication.py",
            "scripts/prepare_deployment_release_channel_publication.py",
            "acceptance_blocking_reasons_absent",
            "local_only_limits_recorded",
            "local provider-plan draft checklist",
            "python scripts/prepare_deployment_release_channel_publication.py --acceptance outputs/deployment_release_channel_acceptance.json --publication-channel local-release-channel-publication --created-at 2026-06-15T04:00:00Z --output outputs/deployment_release_channel_publication_manifest.json",
        ]

        self.assertIn(required_snippets[0], overview)
        self.assertIn(required_snippets[1], migration)
        self.assertIn(required_snippets[2], production)
        self.assertIn(required_snippets[3], publication_doc)
        self.assertIn(required_snippets[4], publication_doc)
        self.assertIn(required_snippets[5], publication_doc)
        self.assertIn(required_snippets[6], publication_doc)
        self.assertIn(required_snippets[7], production)
        self.assertIn(required_snippets[8], runbook)

    def test_production_overview_tracks_deployment_release_channel_evidence_index(self):
        overview = Path("docs/project-overview-and-usage.md").read_text(encoding="utf-8")
        migration = Path("docs/production-grade-migration-plan.md").read_text(encoding="utf-8")
        production = Path("docs/production/README.md").read_text(encoding="utf-8")
        evidence_doc = Path("docs/production/deployment-release-channel-evidence-index.md").read_text(encoding="utf-8")
        runbook = Path("docs/production/operator-runbook.md").read_text(encoding="utf-8")

        required_snippets = [
            "Deployment release-channel evidence index in `src/vyu/deployment/release_channel_evidence.py` and `scripts/build_deployment_release_channel_evidence.py`.",
            "| Deployment release-channel evidence index | `src/vyu/deployment/release_channel_evidence.py` and `scripts/build_deployment_release_channel_evidence.py` | Local release-channel evidence index",
            "Deployment release-channel evidence index: `docs/production/deployment-release-channel-evidence-index.md`",
            "src/vyu/deployment/release_channel_evidence.py",
            "scripts/build_deployment_release_channel_evidence.py",
            "required_evidence_items_present",
            "present_required_evidence_item_count",
            "provider-planning preflight",
            "python scripts/build_deployment_release_channel_evidence.py --publication outputs/deployment_release_channel_publication_manifest.json --index-name local-release-channel-evidence-index --created-at 2026-06-15T04:15:00Z --output outputs/deployment_release_channel_evidence_index.json",
        ]

        self.assertIn(required_snippets[0], overview)
        self.assertIn(required_snippets[1], migration)
        self.assertIn(required_snippets[2], production)
        self.assertIn(required_snippets[3], evidence_doc)
        self.assertIn(required_snippets[4], evidence_doc)
        self.assertIn(required_snippets[5], evidence_doc)
        self.assertIn(required_snippets[6], evidence_doc)
        self.assertIn(required_snippets[7], production)
        self.assertIn(required_snippets[8], runbook)

    def test_production_overview_tracks_deployment_release_channel_export_summary(self):
        overview = Path("docs/project-overview-and-usage.md").read_text(encoding="utf-8")
        migration = Path("docs/production-grade-migration-plan.md").read_text(encoding="utf-8")
        production = Path("docs/production/README.md").read_text(encoding="utf-8")
        export_doc = Path("docs/production/deployment-release-channel-export-summary.md").read_text(encoding="utf-8")
        runbook = Path("docs/production/operator-runbook.md").read_text(encoding="utf-8")

        required_snippets = [
            "Deployment release-channel evidence export summary in `src/vyu/deployment/release_channel_export.py` and `scripts/build_deployment_release_channel_export_summary.py`.",
            "| Deployment release-channel evidence export summary | `src/vyu/deployment/release_channel_export.py` and `scripts/build_deployment_release_channel_export_summary.py` | Local operator review/export checklist",
            "Deployment release-channel evidence export summary: `docs/production/deployment-release-channel-export-summary.md`",
            "src/vyu/deployment/release_channel_export.py",
            "scripts/build_deployment_release_channel_export_summary.py",
            "required_evidence_counts_complete",
            "review_checklist_item_count",
            "provider-planning preflight",
            "python scripts/build_deployment_release_channel_export_summary.py --evidence-index outputs/deployment_release_channel_evidence_index.json --summary-name local-release-channel-evidence-export-summary --created-at 2026-06-15T04:30:00Z --output outputs/deployment_release_channel_export_summary.json",
        ]

        self.assertIn(required_snippets[0], overview)
        self.assertIn(required_snippets[1], migration)
        self.assertIn(required_snippets[2], production)
        self.assertIn(required_snippets[3], export_doc)
        self.assertIn(required_snippets[4], export_doc)
        self.assertIn(required_snippets[5], export_doc)
        self.assertIn(required_snippets[6], export_doc)
        self.assertIn(required_snippets[7], production)
        self.assertIn(required_snippets[8], runbook)

    def test_production_overview_tracks_deployment_release_channel_target_readiness(self):
        overview = Path("docs/project-overview-and-usage.md").read_text(encoding="utf-8")
        migration = Path("docs/production-grade-migration-plan.md").read_text(encoding="utf-8")
        production = Path("docs/production/README.md").read_text(encoding="utf-8")
        target_doc = Path("docs/production/deployment-release-channel-target-readiness.md").read_text(encoding="utf-8")
        runbook = Path("docs/production/operator-runbook.md").read_text(encoding="utf-8")

        required_snippets = [
            "Deployment release-channel target-readiness note in `src/vyu/deployment/release_channel_target.py` and `scripts/build_deployment_release_channel_target_readiness.py`.",
            "| Deployment release-channel target-readiness note | `src/vyu/deployment/release_channel_target.py` and `scripts/build_deployment_release_channel_target_readiness.py` | Local target-selection readiness note",
            "Deployment release-channel target-readiness note: `docs/production/deployment-release-channel-target-readiness.md`",
            "src/vyu/deployment/release_channel_target.py",
            "scripts/build_deployment_release_channel_target_readiness.py",
            "no_target_provider_selected",
            "handoff_checklist_item_count",
            "provider-planning preflight",
            "python scripts/build_deployment_release_channel_target_readiness.py --export-summary outputs/deployment_release_channel_export_summary.json --readiness-name local-release-channel-target-readiness --created-at 2026-06-15T04:45:00Z --output outputs/deployment_release_channel_target_readiness.json",
        ]

        self.assertIn(required_snippets[0], overview)
        self.assertIn(required_snippets[1], migration)
        self.assertIn(required_snippets[2], production)
        self.assertIn(required_snippets[3], target_doc)
        self.assertIn(required_snippets[4], target_doc)
        self.assertIn(required_snippets[5], target_doc)
        self.assertIn(required_snippets[6], target_doc)
        self.assertIn(required_snippets[7], production)
        self.assertIn(required_snippets[8], runbook)

    def test_production_overview_tracks_deployment_release_channel_target_decision(self):
        overview = Path("docs/project-overview-and-usage.md").read_text(encoding="utf-8")
        migration = Path("docs/production-grade-migration-plan.md").read_text(encoding="utf-8")
        production = Path("docs/production/README.md").read_text(encoding="utf-8")
        decision_doc = Path("docs/production/deployment-release-channel-target-decision.md").read_text(encoding="utf-8")
        runbook = Path("docs/production/operator-runbook.md").read_text(encoding="utf-8")

        required_snippets = [
            "Deployment release-channel target decision record in `src/vyu/deployment/release_channel_target_decision.py` and `scripts/decide_deployment_release_channel_target.py`.",
            "| Deployment release-channel target decision record | `src/vyu/deployment/release_channel_target_decision.py` and `scripts/decide_deployment_release_channel_target.py` | Local abstract target-family decision record",
            "Deployment release-channel target decision record: `docs/production/deployment-release-channel-target-decision.md`",
            "src/vyu/deployment/release_channel_target_decision.py",
            "scripts/decide_deployment_release_channel_target.py",
            "choose_requires_candidate_target_family",
            "next_action_count",
            "provider-planning preflight",
            "python scripts/decide_deployment_release_channel_target.py --target-readiness outputs/deployment_release_channel_target_readiness.json --decision choose --target-family serverless_function --operator-id target-operator --operator-role deployment_operator --rationale \"Serverless function selected for provider planning.\" --decided-at 2026-06-15T05:00:00Z --output outputs/deployment_release_channel_target_decision.json",
        ]

        self.assertIn(required_snippets[0], overview)
        self.assertIn(required_snippets[1], migration)
        self.assertIn(required_snippets[2], production)
        self.assertIn(required_snippets[3], decision_doc)
        self.assertIn(required_snippets[4], decision_doc)
        self.assertIn(required_snippets[5], decision_doc)
        self.assertIn(required_snippets[6], decision_doc)
        self.assertIn(required_snippets[7], production)
        self.assertIn(required_snippets[8], runbook)

    def test_production_overview_tracks_deployment_release_channel_provider_preflight(self):
        overview = Path("docs/project-overview-and-usage.md").read_text(encoding="utf-8")
        migration = Path("docs/production-grade-migration-plan.md").read_text(encoding="utf-8")
        production = Path("docs/production/README.md").read_text(encoding="utf-8")
        preflight_doc = Path("docs/production/deployment-release-channel-provider-preflight.md").read_text(encoding="utf-8")
        runbook = Path("docs/production/operator-runbook.md").read_text(encoding="utf-8")

        required_snippets = [
            "Deployment release-channel provider-planning preflight in `src/vyu/deployment/release_channel_provider_preflight.py` and `scripts/build_deployment_release_channel_provider_preflight.py`.",
            "| Deployment release-channel provider-planning preflight | `src/vyu/deployment/release_channel_provider_preflight.py` and `scripts/build_deployment_release_channel_provider_preflight.py` | Local provider-agnostic planning preflight",
            "Deployment release-channel provider-planning preflight: `docs/production/deployment-release-channel-provider-preflight.md`",
            "src/vyu/deployment/release_channel_provider_preflight.py",
            "scripts/build_deployment_release_channel_provider_preflight.py",
            "planning_requirements_recorded",
            "planning_requirement_count",
            "local provider-plan draft checklist",
            "python scripts/build_deployment_release_channel_provider_preflight.py --target-decision outputs/deployment_release_channel_target_decision.json --preflight-name local-release-channel-provider-planning-preflight --created-at 2026-06-15T05:30:00Z --output outputs/deployment_release_channel_provider_preflight.json",
        ]

        self.assertIn(required_snippets[0], overview)
        self.assertIn(required_snippets[1], migration)
        self.assertIn(required_snippets[2], production)
        self.assertIn(required_snippets[3], preflight_doc)
        self.assertIn(required_snippets[4], preflight_doc)
        self.assertIn(required_snippets[5], preflight_doc)
        self.assertIn(required_snippets[6], preflight_doc)
        self.assertIn(required_snippets[7], production)
        self.assertIn(required_snippets[8], runbook)

    def test_production_overview_tracks_deployment_release_channel_provider_decision(self):
        overview = Path("docs/project-overview-and-usage.md").read_text(encoding="utf-8")
        migration = Path("docs/production-grade-migration-plan.md").read_text(encoding="utf-8")
        production = Path("docs/production/README.md").read_text(encoding="utf-8")
        decision_doc = Path("docs/production/deployment-release-channel-provider-decision.md").read_text(encoding="utf-8")
        runbook = Path("docs/production/operator-runbook.md").read_text(encoding="utf-8")

        required_snippets = [
            "Deployment release-channel provider-planning decision record in `src/vyu/deployment/release_channel_provider_decision.py` and `scripts/decide_deployment_release_channel_provider.py`.",
            "| Deployment release-channel provider-planning decision record | `src/vyu/deployment/release_channel_provider_decision.py` and `scripts/decide_deployment_release_channel_provider.py` | Local provider-planning decision record",
            "Deployment release-channel provider-planning decision record: `docs/production/deployment-release-channel-provider-decision.md`",
            "src/vyu/deployment/release_channel_provider_decision.py",
            "scripts/decide_deployment_release_channel_provider.py",
            "proceed_requires_provider_planning_track",
            "next_action_count",
            "local provider-plan draft checklist",
            "python scripts/decide_deployment_release_channel_provider.py --provider-preflight outputs/deployment_release_channel_provider_preflight.json --decision proceed --planning-track serverless_provider_requirements_review --operator-id provider-operator --operator-role deployment_operator --rationale \"Provider planning approved from local preflight.\" --decided-at 2026-06-15T06:00:00Z --output outputs/deployment_release_channel_provider_decision.json",
        ]

        self.assertIn(required_snippets[0], overview)
        self.assertIn(required_snippets[1], migration)
        self.assertIn(required_snippets[2], production)
        self.assertIn(required_snippets[3], decision_doc)
        self.assertIn(required_snippets[4], decision_doc)
        self.assertIn(required_snippets[5], decision_doc)
        self.assertIn(required_snippets[6], decision_doc)
        self.assertIn(required_snippets[7], production)
        self.assertIn(required_snippets[8], runbook)

    def test_production_overview_tracks_connector_health_foundation(self):
        overview = Path("docs/project-overview-and-usage.md").read_text(encoding="utf-8")
        migration = Path("docs/production-grade-migration-plan.md").read_text(encoding="utf-8")

        required_snippets = [
            "Connector health checks and staged PubMed validation records in `src/vyu/connectors/health.py`.",
            "| Connector health foundation | `src/vyu/connectors/health.py` | Health records and staged PubMed replay/live validation records |",
            "| Connector health persistence | `src/vyu/storage/production.py` | SQLite connector health and staged validation records, audit events, readiness checks, and backup/restore support |",
            "SQLite connector health and staged validation persistence in `src/vyu/storage/production.py`.",
            "Production store inspection command with review task, connector readiness, privacy approval, and readiness result readback in `scripts/inspect_production_store.py`.",
            "`docs/production/connector-health-validation.md`",
            "`docs/production/compliance-evidence-bundle.md`",
            "`docs/production/observability-snapshot.md`",
            "`docs/production/incident-recovery-drill.md`",
            "final report-export decision audit events",
        ]

        self.assertIn(required_snippets[0], overview)
        self.assertIn(required_snippets[1], migration)
        self.assertIn(required_snippets[2], migration)
        self.assertIn(required_snippets[3], overview)
        self.assertIn(required_snippets[4], overview)
        self.assertIn(required_snippets[5], overview)
        self.assertIn(required_snippets[6], overview)
        self.assertIn(required_snippets[7], overview)
        self.assertIn(required_snippets[8], overview)
        self.assertIn(required_snippets[9], migration)

    def test_production_overview_tracks_privacy_foundation(self):
        overview = Path("docs/project-overview-and-usage.md").read_text(encoding="utf-8")
        migration = Path("docs/production-grade-migration-plan.md").read_text(encoding="utf-8")
        threat_model = Path("docs/production/threat-model.md").read_text(encoding="utf-8")

        required_snippets = [
            "Privacy data-flow policy and PHI/ePHI gate in `src/vyu/privacy/`.",
            "Framework-neutral privacy approval API and worker adapters in `src/vyu/entrypoints/privacy_approval.py`.",
            "| Privacy foundation | `src/vyu/privacy/` | Data classification, PHI/ePHI fail-closed gate, and approval checks |",
            "| Privacy workflow adapters | `src/vyu/entrypoints/privacy_approval.py` | Framework-neutral API and worker adapters that call the PHI/ePHI gate and persist decisions |",
            "| Privacy approval persistence | `src/vyu/storage/production.py` | SQLite PHI/ePHI gate decision records, audit events, scoped inspection, and backup/restore support |",
            "| Readiness result persistence | `src/vyu/storage/production.py` | SQLite production-readiness check result records, audit events, scoped inspection, and backup/restore support |",
            "| Readiness checks | `scripts/check_production_readiness.py` | Verifies manifest, source, checksum, summary, evaluation, audit, approved review, report-export audit, connector, and scope invariants, then persists scoped readiness results |",
            "SQLite privacy approval persistence and audit events in `src/vyu/storage/production.py`.",
            "SQLite readiness check result persistence and audit events in `src/vyu/storage/production.py`.",
            "Production readiness invariant checks in `scripts/check_production_readiness.py`, including approved review state and allowed report-export audit evidence.",
            "API-shaped and worker-shaped privacy approval adapters call the same PHI/ePHI gate",
            "`docs/production/privacy-data-flow.md`",
            "final report-export decision audit events",
            "PHI/ePHI gate",
        ]

        self.assertIn(required_snippets[0], overview)
        self.assertIn(required_snippets[1], overview)
        self.assertIn(required_snippets[2], migration)
        self.assertIn(required_snippets[3], migration)
        self.assertIn(required_snippets[4], migration)
        self.assertIn(required_snippets[5], migration)
        self.assertIn(required_snippets[6], migration)
        self.assertIn(required_snippets[7], overview)
        self.assertIn(required_snippets[8], overview)
        self.assertIn(required_snippets[9], overview)
        self.assertIn(required_snippets[10], overview)
        self.assertIn(required_snippets[11], overview)
        self.assertIn(required_snippets[12], migration)
        self.assertIn(required_snippets[13], threat_model)

    def test_production_overview_tracks_model_safety_foundation(self):
        overview = Path("docs/project-overview-and-usage.md").read_text(encoding="utf-8")
        migration = Path("docs/production-grade-migration-plan.md").read_text(encoding="utf-8")
        threat_model = Path("docs/production/threat-model.md").read_text(encoding="utf-8")

        required_snippets = [
            "Prompt-injection scan and citation-policy gate in `src/vyu/safety/`.",
            "| Model safety foundation | `src/vyu/safety/` | Prompt-injection signals and citation-policy export gate |",
            "| Safety and report-export decision audit events | `src/vyu/reports/export.py` | Optional production audit events for prompt-injection, citation-policy, and final report-export decisions |",
            "Optional prompt-injection, citation-policy, and report-export decision audit events in `src/vyu/reports/export.py`.",
            "Framework-neutral report-export API and worker adapters in `src/vyu/entrypoints/report_export.py`.",
            "`docs/production/model-safety-policy.md`",
            "final report-export decision audit events",
            "Prompt-injection scan",
        ]

        self.assertIn(required_snippets[0], overview)
        self.assertIn(required_snippets[1], migration)
        self.assertIn(required_snippets[2], migration)
        self.assertIn(required_snippets[3], overview)
        self.assertIn(required_snippets[4], overview)
        self.assertIn(required_snippets[5], overview)
        self.assertIn(required_snippets[6], migration)
        self.assertIn(required_snippets[7], threat_model)

    def test_production_overview_tracks_report_export_foundation(self):
        overview = Path("docs/project-overview-and-usage.md").read_text(encoding="utf-8")
        migration = Path("docs/production-grade-migration-plan.md").read_text(encoding="utf-8")
        security = Path("docs/production/security-architecture.md").read_text(encoding="utf-8")

        required_snippets = [
            "Report export gate in `src/vyu/reports/export.py`.",
            "Framework-neutral report-export route runtime in `src/vyu/entrypoints/report_export_routes.py`.",
            "Storage-backed report export command in `scripts/export_report_from_store.py`.",
            "| Report export foundation | `src/vyu/reports/export.py` | Composes authorization, review, prompt-injection, and citation-policy gates before rendering reports |",
            "| Report export entry adapters | `src/vyu/entrypoints/report_export.py` | Framework-neutral API and worker adapters that call the report export gate |",
            "| Report export route runtime | `src/vyu/entrypoints/report_export_routes.py` | Framework-neutral HTTP-shaped route runtime for report export requests and local phase-output artifact loading |",
            "| Report export operator command | `scripts/export_report_from_store.py` | Loads persisted phase artifacts and review tasks before calling the report export adapter |",
            "`docs/production/report-export-policy.md`",
            "`docs/production/report-export-route-runtime.md`",
            "final report-export decision audit events",
            "Report export paths call authorization, human review, prompt-injection, and citation-policy gates before releasing output.",
        ]

        self.assertIn(required_snippets[0], overview)
        self.assertIn(required_snippets[1], overview)
        self.assertIn(required_snippets[2], overview)
        self.assertIn(required_snippets[3], migration)
        self.assertIn(required_snippets[4], migration)
        self.assertIn(required_snippets[5], migration)
        self.assertIn(required_snippets[6], migration)
        self.assertIn(required_snippets[7], overview)
        self.assertIn(required_snippets[8], overview)
        self.assertIn(required_snippets[9], migration)
        self.assertIn(required_snippets[10], security)

    def test_production_overview_tracks_deployment_runtime_chain(self):
        overview = Path("docs/project-overview-and-usage.md").read_text(encoding="utf-8")
        migration = Path("docs/production-grade-migration-plan.md").read_text(encoding="utf-8")
        production = Path("docs/production/README.md").read_text(encoding="utf-8")

        required_overview = [
            "API service shell for FastAPI/Flask/serverless conversion in `src/vyu/deployment/api_service.py`.",
            "Serverless deployment handler boundary in `src/vyu/deployment/serverless_handler.py`.",
            "Local deployment composition factory in `src/vyu/deployment/composition.py`.",
            "`docs/production/api-service-shell.md`",
            "`docs/production/serverless-handler.md`",
            "`docs/production/deployment-composition.md`",
        ]
        required_migration = [
            "| API service shell | `src/vyu/deployment/api_service.py` | Converts FastAPI/Flask/serverless request shapes into deployment requests and returns framework-neutral or API Gateway-style responses |",
            "| Serverless handler | `src/vyu/deployment/serverless_handler.py` | Callable API Gateway-style packaging boundary that wraps the API service shell and returns stable JSON errors for malformed events |",
            "| Deployment composition | `src/vyu/deployment/composition.py` | Local factory that composes storage, route runtimes, identity mapping, deployment adapter, API shell, and serverless handler from explicit config |",
        ]
        required_production = [
            "API service shell: `docs/production/api-service-shell.md`",
            "Serverless handler: `docs/production/serverless-handler.md`",
            "Deployment composition: `docs/production/deployment-composition.md`",
        ]

        for snippet in required_overview:
            self.assertIn(snippet, overview)
        for snippet in required_migration:
            self.assertIn(snippet, migration)
        for snippet in required_production:
            self.assertIn(snippet, production)

    def test_production_overview_tracks_compliance_attestations(self):
        overview = Path("docs/project-overview-and-usage.md").read_text(encoding="utf-8")
        migration = Path("docs/production-grade-migration-plan.md").read_text(encoding="utf-8")

        required_snippets = [
            "Production compliance attestation command in `scripts/record_compliance_attestation.py`.",
            "The local compliance attestation command records approver decisions against compliance bundle hashes in `outputs/compliance_attestations.jsonl`.",
            "`docs/production/compliance-attestations.md`",
            "| Compliance attestations | `scripts/record_compliance_attestation.py` | Local JSONL approver decisions bound to compliance bundle hashes |",
            "local approver attestation records",
        ]

        self.assertIn(required_snippets[0], overview)
        self.assertIn(required_snippets[1], overview)
        self.assertIn(required_snippets[2], overview)
        self.assertIn(required_snippets[3], migration)
        self.assertIn(required_snippets[4], migration)

    def test_production_overview_tracks_pilot_release_decision(self):
        overview = Path("docs/project-overview-and-usage.md").read_text(encoding="utf-8")
        migration = Path("docs/production-grade-migration-plan.md").read_text(encoding="utf-8")

        required_snippets = [
            "Production pilot release-decision command in `scripts/build_pilot_release_decision.py`.",
            "The local pilot release-decision command combines compliance bundle readiness with required approver attestations and writes `outputs/pilot_release_decision.json`.",
            "`docs/production/pilot-release-decision.md`",
            "| Pilot release decision | `scripts/build_pilot_release_decision.py` | Local go/no-go JSON summary for bundle readiness and required approver attestations |",
            "local pilot release-decision summary",
        ]

        self.assertIn(required_snippets[0], overview)
        self.assertIn(required_snippets[1], overview)
        self.assertIn(required_snippets[2], overview)
        self.assertIn(required_snippets[3], migration)
        self.assertIn(required_snippets[4], migration)


if __name__ == "__main__":
    unittest.main()
