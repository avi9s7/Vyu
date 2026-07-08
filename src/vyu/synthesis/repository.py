from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from src.vyu.research_mcp.hashing import stable_hash
from src.vyu.synthesis.models import (
    Answer,
    AnswerClaim,
    ClaimCitation,
    ModelCall,
    ModelPolicyVersion,
    PromptTemplate,
)


@dataclass(frozen=True)
class ModelPolicyRecord:
    policy_id: UUID
    version_number: int
    status: str
    allowed_providers: tuple[str, ...]
    allowed_models: tuple[str, ...]
    use_cases: tuple[str, ...]
    limits: dict[str, object]
    fallback_rules: dict[str, object]
    sha256: str
    approved_by: str | None = None
    approved_at: str | None = None


@dataclass(frozen=True)
class PromptTemplateRecord:
    template_id: UUID
    name: str
    use_case: str
    version: int
    status: str
    template: str
    output_schema: dict[str, object]
    sha256: str
    approved_by: str | None = None
    approved_at: str | None = None


@dataclass(frozen=True)
class ModelCallRecord:
    call_id: UUID
    tenant_id: UUID
    workspace_id: UUID
    run_id: str
    job_id: UUID | None
    provider_id: str
    model_id: str
    prompt_template_id: str
    prompt_version: str
    policy_version: str
    request_sha256: str
    response_sha256: str | None
    evidence_context_sha256: str
    provider_request_id: str | None
    status: str
    safe_error_code: str | None
    usage: dict[str, object]
    latency_ms: int | None
    estimated_cost_minor: int | None
    currency: str | None


@dataclass(frozen=True)
class AnswerClaimDraft:
    ordinal: int
    text: str
    support_status: str
    citation_ids: tuple[str, ...]
    document_version_id: UUID | None = None
    chunk_id: UUID | None = None


@dataclass(frozen=True)
class AnswerRecord:
    answer_id: UUID
    tenant_id: UUID
    workspace_id: UUID
    research_run_id: UUID
    retrieval_run_id: UUID
    version: int
    status: str
    answer_text: str
    uncertainty: str | None
    limitations: tuple[str, ...]
    model_call_id: UUID
    prompt_version: str
    evidence_context_sha256: str
    claims: tuple[AnswerClaimDraft, ...]
    created_at: str | None = None


@dataclass(frozen=True)
class ModelCallMetrics:
    total_calls: int
    succeeded_calls: int
    failed_calls: int
    blocked_calls: int
    total_input_tokens: int
    total_output_tokens: int
    total_estimated_cost_minor: int
    average_latency_ms: float | None
    errors_by_code: dict[str, int]


class ModelSynthesisRepository:
    def get_active_model_policy(self, session: Session) -> ModelPolicyRecord | None:
        row = session.scalar(
            select(ModelPolicyVersion)
            .where(ModelPolicyVersion.status == "active")
            .order_by(ModelPolicyVersion.version_number.desc())
            .limit(1)
        )
        if not isinstance(row, ModelPolicyVersion):
            return None
        return _model_policy_record(row)

    def create_model_policy_version(
        self,
        session: Session,
        *,
        version_number: int,
        allowed_providers: tuple[str, ...],
        allowed_models: tuple[str, ...],
        use_cases: tuple[str, ...],
        limits: dict[str, object],
        fallback_rules: dict[str, object],
        approved_by: str | None = None,
        status: str = "draft",
    ) -> ModelPolicyRecord:
        payload = {
            "allowed_providers": list(allowed_providers),
            "allowed_models": list(allowed_models),
            "use_cases": list(use_cases),
            "limits": limits,
            "fallback_rules": fallback_rules,
            "version_number": version_number,
        }
        sha256 = stable_hash(payload)
        existing = session.scalar(
            select(ModelPolicyVersion).where(ModelPolicyVersion.sha256 == sha256)
        )
        if isinstance(existing, ModelPolicyVersion):
            return _model_policy_record(existing)
        approved_at = datetime.now(timezone.utc) if status == "active" else None
        row = ModelPolicyVersion(
            id=uuid4(),
            version_number=version_number,
            status=status,
            allowed_providers_json=list(allowed_providers),
            allowed_models_json=list(allowed_models),
            use_cases_json=list(use_cases),
            limits_json=dict(limits),
            fallback_rules_json=dict(fallback_rules),
            approved_by=approved_by,
            approved_at=approved_at,
            sha256=sha256,
        )
        session.add(row)
        session.flush()
        return _model_policy_record(row)

    def activate_model_policy(self, session: Session, *, policy_id: UUID) -> ModelPolicyRecord:
        row = session.scalar(select(ModelPolicyVersion).where(ModelPolicyVersion.id == policy_id))
        if not isinstance(row, ModelPolicyVersion):
            raise KeyError(f"unknown model policy: {policy_id}")
        session.execute(
            update(ModelPolicyVersion)
            .where(ModelPolicyVersion.status == "active")
            .values(status="retired")
        )
        row.status = "active"
        row.approved_at = datetime.now(timezone.utc)
        session.flush()
        return _model_policy_record(row)

    def activate_prompt_template(
        self, session: Session, *, template_id: UUID
    ) -> PromptTemplateRecord:
        row = session.scalar(select(PromptTemplate).where(PromptTemplate.id == template_id))
        if not isinstance(row, PromptTemplate):
            raise KeyError(f"unknown prompt template: {template_id}")
        session.execute(
            update(PromptTemplate)
            .where(
                PromptTemplate.status == "active",
                PromptTemplate.name == row.name,
                PromptTemplate.use_case == row.use_case,
            )
            .values(status="retired")
        )
        row.status = "active"
        row.approved_at = datetime.now(timezone.utc)
        session.flush()
        return _prompt_template_record(row)

    def list_model_policies(self, session: Session) -> tuple[ModelPolicyRecord, ...]:
        rows = session.scalars(
            select(ModelPolicyVersion).order_by(ModelPolicyVersion.version_number.desc())
        ).all()
        return tuple(
            _model_policy_record(row) for row in rows if isinstance(row, ModelPolicyVersion)
        )

    def list_prompt_templates(
        self,
        session: Session,
        *,
        use_case: str | None = None,
    ) -> tuple[PromptTemplateRecord, ...]:
        statement = select(PromptTemplate).order_by(
            PromptTemplate.name.asc(),
            PromptTemplate.version.desc(),
        )
        if use_case is not None:
            statement = statement.where(PromptTemplate.use_case == use_case)
        rows = session.scalars(statement).all()
        return tuple(
            _prompt_template_record(row) for row in rows if isinstance(row, PromptTemplate)
        )

    def get_model_call(self, session: Session, *, call_id: UUID) -> ModelCallRecord | None:
        row = session.scalar(select(ModelCall).where(ModelCall.id == call_id))
        if not isinstance(row, ModelCall):
            return None
        return _model_call_record(row)

    def get_answer_for_research_run(
        self,
        session: Session,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        research_run_id: UUID,
        version: int | None = None,
    ) -> AnswerRecord | None:
        statement = select(Answer).where(
            Answer.tenant_id == tenant_id,
            Answer.workspace_id == workspace_id,
            Answer.research_run_id == research_run_id,
        )
        if version is not None:
            statement = statement.where(Answer.version == version)
        else:
            statement = statement.order_by(Answer.version.desc())
        row = session.scalar(statement.limit(1))
        if not isinstance(row, Answer):
            return None
        return self.get_answer(session, answer_id=row.id)

    def aggregate_model_call_metrics(
        self,
        session: Session,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
    ) -> ModelCallMetrics:
        rows = session.scalars(
            select(ModelCall).where(
                ModelCall.tenant_id == tenant_id,
                ModelCall.workspace_id == workspace_id,
            )
        ).all()
        total_calls = 0
        succeeded_calls = 0
        failed_calls = 0
        blocked_calls = 0
        total_input_tokens = 0
        total_output_tokens = 0
        total_estimated_cost_minor = 0
        latency_total = 0
        latency_count = 0
        errors_by_code: dict[str, int] = {}
        for row in rows:
            if not isinstance(row, ModelCall):
                continue
            total_calls += 1
            if row.status == "succeeded":
                succeeded_calls += 1
            elif row.status == "failed":
                failed_calls += 1
            elif row.status == "blocked":
                blocked_calls += 1
            usage = dict(row.usage_json)
            total_input_tokens += int(usage.get("input_tokens", 0) or 0)
            total_output_tokens += int(usage.get("output_tokens", 0) or 0)
            if row.estimated_cost_minor is not None:
                total_estimated_cost_minor += int(row.estimated_cost_minor)
            if row.latency_ms is not None:
                latency_total += int(row.latency_ms)
                latency_count += 1
            if row.safe_error_code:
                errors_by_code[row.safe_error_code] = errors_by_code.get(row.safe_error_code, 0) + 1
        average_latency_ms = latency_total / latency_count if latency_count else None
        return ModelCallMetrics(
            total_calls=total_calls,
            succeeded_calls=succeeded_calls,
            failed_calls=failed_calls,
            blocked_calls=blocked_calls,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            total_estimated_cost_minor=total_estimated_cost_minor,
            average_latency_ms=average_latency_ms,
            errors_by_code=errors_by_code,
        )

    def create_prompt_template(
        self,
        session: Session,
        *,
        name: str,
        use_case: str,
        version: int,
        template: str,
        output_schema: dict[str, object],
        approved_by: str | None = None,
        status: str = "draft",
    ) -> PromptTemplateRecord:
        payload = {
            "name": name,
            "use_case": use_case,
            "version": version,
            "template": template,
            "output_schema": output_schema,
        }
        sha256 = stable_hash(payload)
        existing = session.scalar(select(PromptTemplate).where(PromptTemplate.sha256 == sha256))
        if isinstance(existing, PromptTemplate):
            return _prompt_template_record(existing)
        row = PromptTemplate(
            id=uuid4(),
            name=name,
            use_case=use_case,
            version=version,
            status=status,
            template=template,
            output_schema_json=dict(output_schema),
            approved_by=approved_by,
            approved_at=datetime.now(timezone.utc) if status == "active" else None,
            sha256=sha256,
        )
        session.add(row)
        session.flush()
        return _prompt_template_record(row)

    def save_model_call(
        self,
        session: Session,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        run_id: str,
        job_id: UUID | None,
        provider_id: str,
        model_id: str,
        prompt_template_id: str,
        prompt_version: str,
        policy_version: str,
        request_sha256: str,
        response_sha256: str | None,
        evidence_context_sha256: str,
        provider_request_id: str | None,
        status: str,
        safe_error_code: str | None,
        usage: dict[str, object],
        latency_ms: int | None,
        estimated_cost_minor: int | None = None,
        currency: str | None = None,
    ) -> ModelCallRecord:
        existing = session.scalar(
            select(ModelCall).where(
                ModelCall.tenant_id == tenant_id,
                ModelCall.request_sha256 == request_sha256,
            )
        )
        if isinstance(existing, ModelCall):
            if existing.status == "pending" and status != "pending":
                existing.status = status
                existing.response_sha256 = response_sha256
                existing.provider_request_id = provider_request_id
                existing.safe_error_code = safe_error_code
                existing.usage_json = dict(usage)
                existing.latency_ms = latency_ms
                existing.estimated_cost_minor = estimated_cost_minor
                existing.currency = currency
                session.flush()
            return _model_call_record(existing)
        row = ModelCall(
            id=uuid4(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            run_id=run_id,
            job_id=job_id,
            provider_id=provider_id,
            model_id=model_id,
            prompt_template_id=prompt_template_id,
            prompt_version=prompt_version,
            policy_version=policy_version,
            request_sha256=request_sha256,
            response_sha256=response_sha256,
            evidence_context_sha256=evidence_context_sha256,
            provider_request_id=provider_request_id,
            status=status,
            safe_error_code=safe_error_code,
            usage_json=dict(usage),
            latency_ms=latency_ms,
            estimated_cost_minor=estimated_cost_minor,
            currency=currency,
        )
        session.add(row)
        session.flush()
        return _model_call_record(row)

    def save_answer(
        self,
        session: Session,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        research_run_id: UUID,
        retrieval_run_id: UUID,
        version: int,
        status: str,
        answer_text: str,
        uncertainty: str | None,
        limitations: tuple[str, ...],
        model_call_id: UUID,
        prompt_version: str,
        evidence_context_sha256: str,
        claims: tuple[AnswerClaimDraft, ...],
    ) -> AnswerRecord:
        existing = session.scalar(
            select(Answer).where(
                Answer.tenant_id == tenant_id,
                Answer.workspace_id == workspace_id,
                Answer.research_run_id == research_run_id,
                Answer.version == version,
            )
        )
        if isinstance(existing, Answer):
            return self.get_answer(session, answer_id=existing.id)
        row = Answer(
            id=uuid4(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            research_run_id=research_run_id,
            retrieval_run_id=retrieval_run_id,
            version=version,
            status=status,
            answer_text=answer_text,
            uncertainty=uncertainty,
            limitations_json=list(limitations),
            model_call_id=model_call_id,
            prompt_version=prompt_version,
            evidence_context_sha256=evidence_context_sha256,
        )
        session.add(row)
        session.flush()
        for claim in claims:
            claim_row = AnswerClaim(
                id=uuid4(),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                answer_id=row.id,
                ordinal=claim.ordinal,
                text=claim.text,
                support_status=claim.support_status,
            )
            session.add(claim_row)
            session.flush()
            for citation_id in claim.citation_ids:
                session.add(
                    ClaimCitation(
                        id=uuid4(),
                        tenant_id=tenant_id,
                        workspace_id=workspace_id,
                        claim_id=claim_row.id,
                        citation_id=citation_id,
                        document_version_id=claim.document_version_id,
                        chunk_id=claim.chunk_id,
                    )
                )
        session.flush()
        return self.get_answer(session, answer_id=row.id)

    def get_answer(self, session: Session, *, answer_id: UUID) -> AnswerRecord:
        row = session.scalar(select(Answer).where(Answer.id == answer_id))
        if not isinstance(row, Answer):
            raise KeyError(f"unknown answer: {answer_id}")
        claim_rows = session.scalars(
            select(AnswerClaim)
            .where(AnswerClaim.answer_id == answer_id)
            .order_by(AnswerClaim.ordinal.asc())
        ).all()
        claims: list[AnswerClaimDraft] = []
        for claim_row in claim_rows:
            if not isinstance(claim_row, AnswerClaim):
                continue
            citations = session.scalars(
                select(ClaimCitation).where(ClaimCitation.claim_id == claim_row.id)
            ).all()
            claims.append(
                AnswerClaimDraft(
                    ordinal=claim_row.ordinal,
                    text=claim_row.text,
                    support_status=claim_row.support_status,
                    citation_ids=tuple(
                        citation.citation_id
                        for citation in citations
                        if isinstance(citation, ClaimCitation)
                    ),
                )
            )
        limitations = row.limitations_json
        return AnswerRecord(
            answer_id=row.id,
            tenant_id=row.tenant_id,
            workspace_id=row.workspace_id,
            research_run_id=row.research_run_id,
            retrieval_run_id=row.retrieval_run_id,
            version=row.version,
            status=row.status,
            answer_text=row.answer_text,
            uncertainty=row.uncertainty,
            limitations=tuple(str(item) for item in limitations) if isinstance(limitations, list) else (),
            model_call_id=row.model_call_id,
            prompt_version=row.prompt_version,
            evidence_context_sha256=row.evidence_context_sha256,
            claims=tuple(claims),
            created_at=row.created_at.isoformat() if row.created_at is not None else None,
        )

    def next_answer_version(
        self,
        session: Session,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        research_run_id: UUID,
    ) -> int:
        current = session.scalar(
            select(func.max(Answer.version)).where(
                Answer.tenant_id == tenant_id,
                Answer.workspace_id == workspace_id,
                Answer.research_run_id == research_run_id,
            )
        )
        return int(current or 0) + 1


def _model_policy_record(row: ModelPolicyVersion) -> ModelPolicyRecord:
    return ModelPolicyRecord(
        policy_id=row.id,
        version_number=row.version_number,
        status=row.status,
        allowed_providers=tuple(str(item) for item in row.allowed_providers_json),
        allowed_models=tuple(str(item) for item in row.allowed_models_json),
        use_cases=tuple(str(item) for item in row.use_cases_json),
        limits=dict(row.limits_json),
        fallback_rules=dict(row.fallback_rules_json),
        sha256=row.sha256,
        approved_by=row.approved_by,
        approved_at=row.approved_at.isoformat() if row.approved_at is not None else None,
    )


def _prompt_template_record(row: PromptTemplate) -> PromptTemplateRecord:
    return PromptTemplateRecord(
        template_id=row.id,
        name=row.name,
        use_case=row.use_case,
        version=row.version,
        status=row.status,
        template=row.template,
        output_schema=dict(row.output_schema_json),
        sha256=row.sha256,
        approved_by=row.approved_by,
        approved_at=row.approved_at.isoformat() if row.approved_at is not None else None,
    )


def _model_call_record(row: ModelCall) -> ModelCallRecord:
    return ModelCallRecord(
        call_id=row.id,
        tenant_id=row.tenant_id,
        workspace_id=row.workspace_id,
        run_id=row.run_id,
        job_id=row.job_id,
        provider_id=row.provider_id,
        model_id=row.model_id,
        prompt_template_id=row.prompt_template_id,
        prompt_version=row.prompt_version,
        policy_version=row.policy_version,
        request_sha256=row.request_sha256,
        response_sha256=row.response_sha256,
        evidence_context_sha256=row.evidence_context_sha256,
        provider_request_id=row.provider_request_id,
        status=row.status,
        safe_error_code=row.safe_error_code,
        usage=dict(row.usage_json),
        latency_ms=row.latency_ms,
        estimated_cost_minor=row.estimated_cost_minor,
        currency=row.currency,
    )
