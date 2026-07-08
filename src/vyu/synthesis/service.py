from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.vyu.db.repositories.audit import AuditRepository, NewAuditEvent
from src.vyu.jobs.contracts import JobRecord
from src.vyu.jobs.models import Job, OutboxEvent, ResearchRun
from src.vyu.model_gateway.contracts import ModelPolicy, ModelRequest
from src.vyu.model_gateway.errors import (
    GatewayError,
    GatewayMalformedResponse,
    GatewayPolicyBlocked,
    GatewayRateLimited,
    GatewayTimeout,
    GatewayUnavailable,
)
from src.vyu.model_gateway.gateway import ModelGateway
from src.vyu.research.repository import TERMINAL_RESEARCH_STATUSES, ResearchExecutionRepository
from src.vyu.synthesis.context import BuiltEvidenceContext, EvidenceContextBuildError, EvidenceContextBuilder, EvidenceContextItem
from src.vyu.synthesis.contracts import (
    GROUNDED_ANSWER_PROMPT_NAME,
    GROUNDED_ANSWER_SCHEMA_VERSION,
    GROUNDED_SYNTHESIS_USE_CASE,
)
from src.vyu.synthesis.prompt_config import (
    GROUNDED_ANSWER_OUTPUT_JSON_SCHEMA,
    GROUNDED_ANSWER_SYSTEM_PROMPT,
    render_grounded_answer_user_prompt,
)
from src.vyu.synthesis.repository import AnswerClaimDraft, ModelPolicyRecord, ModelSynthesisRepository
from src.vyu.synthesis.schema import (
    GroundedAnswerOutput,
    GroundedAnswerSemanticValidationError,
    parse_grounded_answer_output,
)
from src.vyu.synthesis.validators import (
    SynthesisValidationResult,
    required_abstention_reason,
    validate_synthesis_output,
)


@dataclass(frozen=True)
class SynthesisSettings:
    max_context_tokens: int = 8_000
    max_output_tokens: int = 2_048
    max_answer_chars: int = 8_000
    max_claims: int = 32
    timeout_seconds: int = 120
    temperature: float = 0.0
    default_provider_id: str = "deterministic"
    default_model_id: str = "vyu-deterministic-v1"


@dataclass(frozen=True)
class SynthesisExecutionResult:
    outcome: str
    result: dict[str, object] | None = None
    error_code: str | None = None
    retryable: bool = False


@dataclass
class SynthesisExecutor:
    gateway: ModelGateway
    repository: ModelSynthesisRepository
    research_repository: ResearchExecutionRepository
    context_builder: EvidenceContextBuilder
    settings: SynthesisSettings = SynthesisSettings()
    clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC)

    def execute(
        self,
        job: JobRecord,
        *,
        session: Session,
        heartbeat: Callable[[], None],
    ) -> SynthesisExecutionResult:
        del heartbeat
        if job.payload.get("simulate") is not None:
            return self._simulate(job.payload)

        research_run_id = UUID(str(job.payload["research_run_id"]))
        retrieval_run_id = UUID(str(job.payload["retrieval_run_id"]))
        run = self.research_repository.get_run(session, research_run_id)
        if run is None:
            return SynthesisExecutionResult(
                outcome="terminal_failure",
                error_code="research_run_not_found",
            )

        if run.status in TERMINAL_RESEARCH_STATUSES:
            return SynthesisExecutionResult(
                outcome="complete",
                result=self._terminal_result(run),
            )

        if self._is_cancelled(session, job, run):
            self._set_run_status(session, run, "cancelled", current_step="cancelled")
            run.completed_at = self.clock()
            return SynthesisExecutionResult(
                outcome="complete",
                result={"status": "cancelled", "research_run_id": str(run.id)},
            )

        policy_record = self.repository.get_active_model_policy(session)
        if policy_record is None:
            return self._fail_run(
                session,
                run,
                status="blocked",
                step="synthesis_policy",
                error_code="model_policy_missing",
                message="No active model policy is configured for synthesis.",
            )

        prompt_version = GROUNDED_ANSWER_SCHEMA_VERSION
        gateway = self._gateway_for_policy(policy_record, prompt_version=prompt_version)
        provider_id = str(job.payload.get("provider_id", self.settings.default_provider_id))
        model_id = str(job.payload.get("model_id", self.settings.default_model_id))

        self._set_run_status(session, run, "synthesizing", current_step="synthesis_context")
        self.research_repository.append_event(
            session,
            run=run,
            event_type="synthesis_started",
            safe_message="Synthesis started.",
            details={"retrieval_run_id": str(retrieval_run_id)},
        )

        try:
            context = self.context_builder.build_from_session(
                session,
                tenant_id=job.tenant_id,
                workspace_id=job.workspace_id,
                research_run_id=research_run_id,
                retrieval_run_id=retrieval_run_id,
                max_tokens=self.settings.max_context_tokens,
            )
        except EvidenceContextBuildError as exc:
            return self._fail_run(
                session,
                run,
                status="blocked",
                step="synthesis_context",
                error_code="evidence_context_invalid",
                message="Evidence context could not be built safely.",
                details={"reason": str(exc)},
            )

        abstention_reason = required_abstention_reason(context)
        if abstention_reason is not None:
            return self._persist_deterministic_abstention(
                session,
                job=job,
                run=run,
                context=context,
                retrieval_run_id=retrieval_run_id,
                policy_record=policy_record,
                abstention_reason=abstention_reason,
                provider_id=provider_id,
                model_id=model_id,
                prompt_version=prompt_version,
            )

        user_prompt = render_grounded_answer_user_prompt(
            question=run.question,
            evidence_block=context.to_prompt_block(),
        )
        limits = dict(policy_record.limits)
        allow_schema_repair = bool(policy_record.fallback_rules.get("allow_schema_repair", False))
        provider_fallbacks = _provider_fallbacks(policy_record.fallback_rules)

        generation = self._generate_with_validation(
            gateway=gateway,
            session=session,
            job=job,
            run=run,
            context=context,
            policy_record=policy_record,
            provider_id=provider_id,
            model_id=model_id,
            prompt_version=prompt_version,
            user_prompt=user_prompt,
            required_abstention=None,
            allow_schema_repair=allow_schema_repair,
            provider_fallbacks=provider_fallbacks,
            limits=limits,
        )
        if generation.outcome != "complete":
            return generation

        assert generation.result is not None
        return self._persist_success(
            session,
            job=job,
            run=run,
            context=context,
            retrieval_run_id=retrieval_run_id,
            policy_record=policy_record,
            provider_id=str(generation.result["provider_id"]),
            model_id=str(generation.result["model_id"]),
            prompt_version=prompt_version,
            model_call_id=UUID(str(generation.result["model_call_id"])),
            parsed_output=generation.result["parsed_output"],
            validation=generation.result["validation"],
            repair_attempted=bool(generation.result.get("repair_attempted")),
        )

    def _generate_with_validation(
        self,
        *,
        gateway: ModelGateway,
        session: Session,
        job: JobRecord,
        run: ResearchRun,
        context: BuiltEvidenceContext,
        policy_record: ModelPolicyRecord,
        provider_id: str,
        model_id: str,
        prompt_version: str,
        user_prompt: str,
        required_abstention: str | None,
        allow_schema_repair: bool,
        provider_fallbacks: Mapping[str, str],
        limits: dict[str, object],
        repair_attempted: bool = False,
        validation_errors: tuple[str, ...] | None = None,
    ) -> SynthesisExecutionResult:
        request = self._build_model_request(
            job=job,
            run=run,
            context=context,
            policy_record=policy_record,
            provider_id=provider_id,
            model_id=model_id,
            prompt_version=prompt_version,
            user_prompt=user_prompt,
            repair_errors=validation_errors,
        )
        self._set_run_status(session, run, "synthesizing", current_step="synthesis_model_call")
        self.repository.save_model_call(
            session,
            tenant_id=job.tenant_id,
            workspace_id=job.workspace_id,
            run_id=str(run.id),
            job_id=job.id,
            provider_id=provider_id,
            model_id=model_id,
            prompt_template_id=GROUNDED_ANSWER_PROMPT_NAME,
            prompt_version=prompt_version,
            policy_version=str(policy_record.version_number),
            request_sha256=request.request_sha256(),
            response_sha256=None,
            evidence_context_sha256=context.context_sha256,
            provider_request_id=None,
            status="pending",
            safe_error_code=None,
            usage={},
            latency_ms=None,
        )

        try:
            response = gateway.generate(request)
        except GatewayPolicyBlocked as exc:
            self.repository.save_model_call(
                session,
                tenant_id=job.tenant_id,
                workspace_id=job.workspace_id,
                run_id=str(run.id),
                job_id=job.id,
                provider_id=provider_id,
                model_id=model_id,
                prompt_template_id=GROUNDED_ANSWER_PROMPT_NAME,
                prompt_version=prompt_version,
                policy_version=str(policy_record.version_number),
                request_sha256=request.request_sha256(),
                response_sha256=None,
                evidence_context_sha256=context.context_sha256,
                provider_request_id=None,
                status="blocked",
                safe_error_code=exc.safe_code,
                usage={},
                latency_ms=None,
            )
            return self._fail_run(
                session,
                run,
                status="blocked",
                step="synthesis_model_call",
                error_code=exc.safe_code,
                message="Model provider blocked synthesis.",
            )
        except (GatewayRateLimited, GatewayTimeout, GatewayUnavailable) as exc:
            self.repository.save_model_call(
                session,
                tenant_id=job.tenant_id,
                workspace_id=job.workspace_id,
                run_id=str(run.id),
                job_id=job.id,
                provider_id=provider_id,
                model_id=model_id,
                prompt_template_id=GROUNDED_ANSWER_PROMPT_NAME,
                prompt_version=prompt_version,
                policy_version=str(policy_record.version_number),
                request_sha256=request.request_sha256(),
                response_sha256=None,
                evidence_context_sha256=context.context_sha256,
                provider_request_id=None,
                status="failed",
                safe_error_code=exc.safe_code,
                usage={},
                latency_ms=None,
            )
            return SynthesisExecutionResult(
                outcome="retry",
                error_code=exc.safe_code,
                retryable=True,
            )
        except GatewayMalformedResponse as exc:
            if allow_schema_repair and not repair_attempted:
                return self._generate_with_validation(
                    gateway=gateway,
                    session=session,
                    job=job,
                    run=run,
                    context=context,
                    policy_record=policy_record,
                    provider_id=provider_id,
                    model_id=model_id,
                    prompt_version=prompt_version,
                    user_prompt=user_prompt,
                    required_abstention=required_abstention,
                    allow_schema_repair=False,
                    provider_fallbacks=provider_fallbacks,
                    limits=limits,
                    repair_attempted=True,
                    validation_errors=(str(exc),),
                )
            return self._fail_run(
                session,
                run,
                status="failed",
                step="synthesis_model_call",
                error_code=exc.safe_code,
                message="Model returned malformed synthesis output.",
            )
        except GatewayError as exc:
            fallback_provider = provider_fallbacks.get(provider_id)
            if fallback_provider and not repair_attempted:
                return self._generate_with_validation(
                    gateway=gateway,
                    session=session,
                    job=job,
                    run=run,
                    context=context,
                    policy_record=policy_record,
                    provider_id=fallback_provider,
                    model_id=model_id,
                    prompt_version=prompt_version,
                    user_prompt=user_prompt,
                    required_abstention=required_abstention,
                    allow_schema_repair=allow_schema_repair,
                    provider_fallbacks={},
                    limits=limits,
                    repair_attempted=True,
                )
            return self._fail_run(
                session,
                run,
                status="failed",
                step="synthesis_model_call",
                error_code=exc.safe_code,
                message="Model synthesis call failed.",
            )

        try:
            parsed_output = parse_grounded_answer_output(response.output)
        except GroundedAnswerSemanticValidationError as exc:
            if allow_schema_repair and not repair_attempted:
                return self._generate_with_validation(
                    gateway=gateway,
                    session=session,
                    job=job,
                    run=run,
                    context=context,
                    policy_record=policy_record,
                    provider_id=provider_id,
                    model_id=model_id,
                    prompt_version=prompt_version,
                    user_prompt=user_prompt,
                    required_abstention=required_abstention,
                    allow_schema_repair=False,
                    provider_fallbacks=provider_fallbacks,
                    limits=limits,
                    repair_attempted=True,
                    validation_errors=exc.errors,
                )
            return self._fail_run(
                session,
                run,
                status="failed",
                step="synthesis_validation",
                error_code="synthesis_schema_invalid",
                message="Model output did not match the grounded answer schema.",
                details={"errors": list(exc.errors)},
            )

        validation = validate_synthesis_output(
            parsed_output,
            context=context,
            required_abstention=required_abstention,
            max_answer_chars=int(limits.get("max_answer_chars", self.settings.max_answer_chars)),
            max_claims=int(limits.get("max_claims", self.settings.max_claims)),
        )
        if not validation.valid:
            if allow_schema_repair and not repair_attempted:
                return self._generate_with_validation(
                    gateway=gateway,
                    session=session,
                    job=job,
                    run=run,
                    context=context,
                    policy_record=policy_record,
                    provider_id=provider_id,
                    model_id=model_id,
                    prompt_version=prompt_version,
                    user_prompt=user_prompt,
                    required_abstention=required_abstention,
                    allow_schema_repair=False,
                    provider_fallbacks=provider_fallbacks,
                    limits=limits,
                    repair_attempted=True,
                    validation_errors=validation.errors,
                )
            return self._fail_run(
                session,
                run,
                status="blocked",
                step="synthesis_validation",
                error_code="synthesis_validation_failed",
                message="Synthesis output failed post-generation validation.",
                details={"errors": list(validation.errors)},
            )

        model_call = self.repository.save_model_call(
            session,
            tenant_id=job.tenant_id,
            workspace_id=job.workspace_id,
            run_id=str(run.id),
            job_id=job.id,
            provider_id=provider_id,
            model_id=model_id,
            prompt_template_id=GROUNDED_ANSWER_PROMPT_NAME,
            prompt_version=prompt_version,
            policy_version=str(policy_record.version_number),
            request_sha256=request.request_sha256(),
            response_sha256=response.response_sha256,
            evidence_context_sha256=context.context_sha256,
            provider_request_id=response.provider_request_id,
            status="succeeded",
            safe_error_code=None,
            usage={
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "reasoning_tokens": response.reasoning_tokens,
                "cached_tokens": response.cached_tokens,
            },
            latency_ms=response.latency_ms,
        )
        return SynthesisExecutionResult(
            outcome="complete",
            result={
                "provider_id": provider_id,
                "model_id": model_id,
                "model_call_id": str(model_call.call_id),
                "parsed_output": parsed_output,
                "validation": validation,
                "repair_attempted": repair_attempted,
            },
        )

    def _persist_success(
        self,
        session: Session,
        *,
        job: JobRecord,
        run: ResearchRun,
        context: BuiltEvidenceContext,
        retrieval_run_id: UUID,
        policy_record: ModelPolicyRecord,
        provider_id: str,
        model_id: str,
        prompt_version: str,
        model_call_id: UUID,
        parsed_output: GroundedAnswerOutput,
        validation: SynthesisValidationResult,
        repair_attempted: bool,
    ) -> SynthesisExecutionResult:
        answer_version = self.repository.next_answer_version(
            session,
            tenant_id=job.tenant_id,
            workspace_id=job.workspace_id,
            research_run_id=run.id,
        )
        claims = tuple(
            AnswerClaimDraft(
                ordinal=index,
                text=claim.claim_text,
                support_status=claim.support,
                citation_ids=tuple(claim.citation_ids),
                document_version_id=_citation_lookup(context, claim.citation_ids[0]).document_version_id
                if claim.citation_ids
                else None,
                chunk_id=_citation_lookup(context, claim.citation_ids[0]).document_chunk_id
                if claim.citation_ids
                else None,
            )
            for index, claim in enumerate(parsed_output.claims, start=1)
        )
        answer = self.repository.save_answer(
            session,
            tenant_id=job.tenant_id,
            workspace_id=job.workspace_id,
            research_run_id=run.id,
            retrieval_run_id=retrieval_run_id,
            version=answer_version,
            status="draft",
            answer_text=parsed_output.answer_summary,
            uncertainty=parsed_output.uncertainty or None,
            limitations=tuple(parsed_output.limitations),
            model_call_id=model_call_id,
            prompt_version=prompt_version,
            evidence_context_sha256=context.context_sha256,
            claims=claims,
        )
        if not self._append_audit_and_events(
            session,
            job=job,
            run=run,
            answer_id=answer.answer_id,
            context=context,
            validation=validation,
            repair_attempted=repair_attempted,
            abstained=False,
        ):
            return self._fail_run(
                session,
                run,
                status="failed",
                step="synthesis_audit",
                error_code="audit_persist_failed",
                message="Synthesis audit persistence failed.",
            )

        self._set_run_status(session, run, "review_required", current_step="governance_review")
        self._enqueue_governance(session, job=job, run=run, answer_id=answer.answer_id)
        session.flush()
        return SynthesisExecutionResult(
            outcome="complete",
            result={
                "status": "review_required",
                "research_run_id": str(run.id),
                "answer_id": str(answer.answer_id),
                "answer_version": answer.version,
                "abstained": parsed_output.abstained,
                "validation_warnings": [
                    {"code": warning.code, "message": warning.message}
                    for warning in validation.warnings
                ],
            },
        )

    def _persist_deterministic_abstention(
        self,
        session: Session,
        *,
        job: JobRecord,
        run: ResearchRun,
        context: BuiltEvidenceContext,
        retrieval_run_id: UUID,
        policy_record: ModelPolicyRecord,
        abstention_reason: str,
        provider_id: str,
        model_id: str,
        prompt_version: str,
    ) -> SynthesisExecutionResult:
        parsed_output = GroundedAnswerOutput(
            answer_summary=_abstention_summary(abstention_reason),
            claims=[],
            uncertainty="No usable evidence remained after deterministic context filtering.",
            contradictions=[],
            limitations=[],
            abstained=True,
            abstention_reason=abstention_reason,
        )
        request = self._build_model_request(
            job=job,
            run=run,
            context=context,
            policy_record=policy_record,
            provider_id=provider_id,
            model_id=model_id,
            prompt_version=prompt_version,
            user_prompt=render_grounded_answer_user_prompt(
                question=run.question,
                evidence_block=context.to_prompt_block(),
            ),
        )
        model_call = self.repository.save_model_call(
            session,
            tenant_id=job.tenant_id,
            workspace_id=job.workspace_id,
            run_id=str(run.id),
            job_id=job.id,
            provider_id=provider_id,
            model_id=model_id,
            prompt_template_id=GROUNDED_ANSWER_PROMPT_NAME,
            prompt_version=prompt_version,
            policy_version=str(policy_record.version_number),
            request_sha256=request.request_sha256(),
            response_sha256=None,
            evidence_context_sha256=context.context_sha256,
            provider_request_id=None,
            status="blocked",
            safe_error_code="deterministic_abstention",
            usage={},
            latency_ms=0,
        )
        answer_version = self.repository.next_answer_version(
            session,
            tenant_id=job.tenant_id,
            workspace_id=job.workspace_id,
            research_run_id=run.id,
        )
        answer = self.repository.save_answer(
            session,
            tenant_id=job.tenant_id,
            workspace_id=job.workspace_id,
            research_run_id=run.id,
            retrieval_run_id=retrieval_run_id,
            version=answer_version,
            status="draft",
            answer_text=parsed_output.answer_summary,
            uncertainty=parsed_output.uncertainty,
            limitations=(),
            model_call_id=model_call.call_id,
            prompt_version=prompt_version,
            evidence_context_sha256=context.context_sha256,
            claims=(),
        )
        validation = validate_synthesis_output(
            parsed_output,
            context=context,
            required_abstention=abstention_reason,
            max_answer_chars=self.settings.max_answer_chars,
            max_claims=self.settings.max_claims,
        )
        if not self._append_audit_and_events(
            session,
            job=job,
            run=run,
            answer_id=answer.answer_id,
            context=context,
            validation=validation,
            repair_attempted=False,
            abstained=True,
        ):
            return self._fail_run(
                session,
                run,
                status="failed",
                step="synthesis_audit",
                error_code="audit_persist_failed",
                message="Synthesis audit persistence failed.",
            )
        self._set_run_status(session, run, "review_required", current_step="governance_review")
        self._enqueue_governance(session, job=job, run=run, answer_id=answer.answer_id)
        session.flush()
        return SynthesisExecutionResult(
            outcome="complete",
            result={
                "status": "review_required",
                "research_run_id": str(run.id),
                "answer_id": str(answer.answer_id),
                "answer_version": answer.version,
                "abstained": True,
                "abstention_reason": abstention_reason,
            },
        )

    def _append_audit_and_events(
        self,
        session: Session,
        *,
        job: JobRecord,
        run: ResearchRun,
        answer_id: UUID,
        context: BuiltEvidenceContext,
        validation: SynthesisValidationResult,
        repair_attempted: bool,
        abstained: bool,
    ) -> bool:
        if bool(job.payload.get("fail_audit")):
            return False
        self.research_repository.append_event(
            session,
            run=run,
            event_type="synthesis_completed",
            safe_message="Grounded synthesis completed.",
            details={
                "answer_id": str(answer_id),
                "abstained": abstained,
                "repair_attempted": repair_attempted,
                "validation_warnings": [
                    {"code": warning.code, "message": warning.message}
                    for warning in validation.warnings
                ],
            },
        )
        AuditRepository(session).append(
            NewAuditEvent(
                id=uuid4(),
                tenant_id=job.tenant_id,
                workspace_id=job.workspace_id,
                actor_type="system",
                actor_id="synthesis-worker",
                request_id=str(job.id),
                trace_id=str(job.id),
                event_type="synthesis_answer_persisted",
                resource_type="answer",
                resource_id=str(answer_id),
                outcome="success",
                payload_sha256=context.context_sha256,
                details={
                    "research_run_id": str(run.id),
                    "abstained": abstained,
                    "repair_attempted": repair_attempted,
                },
            )
        )
        return True

    def _enqueue_governance(
        self,
        session: Session,
        *,
        job: JobRecord,
        run: ResearchRun,
        answer_id: UUID,
    ) -> None:
        outbox_id = uuid4()
        session.add(
            OutboxEvent(
                id=outbox_id,
                tenant_id=job.tenant_id,
                workspace_id=job.workspace_id,
                topic="governance",
                aggregate_type="research_run",
                aggregate_id=str(run.id),
                payload={
                    "schema_version": 1,
                    "message_id": str(outbox_id),
                    "kind": "governance.review",
                    "research_run_id": str(run.id),
                    "answer_id": str(answer_id),
                    "tenant_id": str(job.tenant_id),
                    "workspace_id": str(job.workspace_id),
                    "created_at": self.clock().isoformat(),
                },
            )
        )

    def _build_model_request(
        self,
        *,
        job: JobRecord,
        run: ResearchRun,
        context: BuiltEvidenceContext,
        policy_record: ModelPolicyRecord,
        provider_id: str,
        model_id: str,
        prompt_version: str,
        user_prompt: str,
        repair_errors: tuple[str, ...] | None = None,
    ) -> ModelRequest:
        input_text = user_prompt
        if repair_errors:
            input_text = (
                f"{user_prompt}\n\n"
                "Previous response failed validation:\n"
                + "\n".join(f"- {error}" for error in repair_errors)
                + "\nReturn corrected JSON only."
            )
        request_id = str(job.payload.get("request_id") or job.id)
        if repair_errors:
            request_id = f"{request_id}:repair"
        limits = dict(policy_record.limits)
        return ModelRequest(
            request_id=request_id,
            tenant_id=job.tenant_id,
            workspace_id=job.workspace_id,
            run_id=str(run.id),
            use_case=GROUNDED_SYNTHESIS_USE_CASE,
            provider_id=provider_id,
            model_id=model_id,
            prompt_template_id=GROUNDED_ANSWER_PROMPT_NAME,
            prompt_version=prompt_version,
            system_instructions=GROUNDED_ANSWER_SYSTEM_PROMPT,
            input=input_text,
            output_schema=dict(GROUNDED_ANSWER_OUTPUT_JSON_SCHEMA),
            max_output_tokens=int(limits.get("max_output_tokens", self.settings.max_output_tokens)),
            timeout_seconds=int(limits.get("timeout_seconds", self.settings.timeout_seconds)),
            temperature=float(limits.get("temperature", self.settings.temperature)),
            evidence_context_sha256=context.context_sha256,
            policy_version=str(policy_record.version_number),
        )

    def _gateway_for_policy(
        self,
        policy_record: ModelPolicyRecord,
        *,
        prompt_version: str,
    ) -> ModelGateway:
        limits = dict(policy_record.limits)
        policy = ModelPolicy(
            policy_version=str(policy_record.version_number),
            allowed_providers=frozenset(policy_record.allowed_providers),
            allowed_models=frozenset(policy_record.allowed_models),
            allowed_use_cases=frozenset(policy_record.use_cases),
            allowed_prompt_versions=frozenset({prompt_version}),
            max_output_tokens=int(limits.get("max_output_tokens", self.settings.max_output_tokens)),
            max_context_bytes=int(limits.get("max_context_bytes", 512_000)),
            max_output_schema_properties=int(limits.get("max_output_schema_properties", 64)),
        )
        return ModelGateway(
            policy=policy,
            generation_adapters=self.gateway.generation_adapters,
            embedding_adapters=self.gateway.embedding_adapters,
            health_adapters=self.gateway.health_adapters,
        )

    def _fail_run(
        self,
        session: Session,
        run: ResearchRun,
        *,
        status: str,
        step: str,
        error_code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> SynthesisExecutionResult:
        self._set_run_status(session, run, status, current_step=step)
        self.research_repository.append_event(
            session,
            run=run,
            event_type="synthesis_failed",
            safe_message=message,
            details={"error_code": error_code, **(details or {})},
        )
        session.flush()
        return SynthesisExecutionResult(outcome="terminal_failure", error_code=error_code)

    def _simulate(self, payload: dict[str, object]) -> SynthesisExecutionResult:
        simulate = payload.get("simulate")
        if simulate == "retry":
            return SynthesisExecutionResult(outcome="retry", error_code="transient", retryable=True)
        if simulate == "fail":
            return SynthesisExecutionResult(outcome="terminal_failure", error_code="policy_blocked")
        if simulate == "raise":
            raise RuntimeError("simulated synthesis handler crash")
        return SynthesisExecutionResult(outcome="complete", result={"status": "processed"})

    def _is_cancelled(self, session: Session, job: JobRecord, run: ResearchRun) -> bool:
        if run.cancel_requested:
            return True
        current_job = session.scalar(select(Job).where(Job.id == job.id))
        return current_job is not None and current_job.status == "cancelled"

    def _set_run_status(
        self,
        session: Session,
        run: ResearchRun,
        status: str,
        *,
        current_step: str | None,
    ) -> None:
        run.status = status
        run.current_step = current_step
        if run.started_at is None and status not in {"queued"}:
            run.started_at = self.clock()
        session.flush()

    def _terminal_result(self, run: ResearchRun) -> dict[str, object]:
        return {
            "status": run.status,
            "research_run_id": str(run.id),
            "current_step": run.current_step,
        }


def _provider_fallbacks(fallback_rules: dict[str, object]) -> dict[str, str]:
    raw = fallback_rules.get("generation_provider_fallback")
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items()}


def _abstention_summary(reason: str) -> str:
    messages = {
        "insufficient_evidence": (
            "Vyu cannot provide a grounded answer because no usable evidence "
            "remained after retrieval and policy filtering."
        ),
        "all_evidence_retracted": (
            "Vyu cannot provide a grounded answer because all retrieved evidence "
            "is retracted."
        ),
        "evidence_revoked": (
            "Vyu cannot provide a grounded answer because required sources were "
            "revoked after the retrieval run."
        ),
    }
    return messages.get(
        reason,
        "Vyu cannot provide a grounded answer with the available evidence.",
    )


def _citation_lookup(context: BuiltEvidenceContext, citation_id: str) -> EvidenceContextItem:
    for item in context.items:
        if item.citation_id == citation_id:
            return item
    raise KeyError(citation_id)
