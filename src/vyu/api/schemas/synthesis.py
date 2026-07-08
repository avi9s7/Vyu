from __future__ import annotations

from pydantic import BaseModel, Field

MODEL_POLICY_ACTIVATE_ROUTE = "POST /v1/admin/model-gateway/policies/{policy_id}/activate"
PROMPT_TEMPLATE_ACTIVATE_ROUTE = "POST /v1/admin/model-gateway/prompts/{template_id}/activate"


class AnswerCitationItem(BaseModel):
    citation_id: str
    document_version_id: str | None = None
    chunk_id: str | None = None


class AnswerClaimItem(BaseModel):
    ordinal: int
    claim_text: str
    support_status: str
    citation_ids: list[str]
    citations: list[AnswerCitationItem] = Field(default_factory=list)


class AnswerVersionLinks(BaseModel):
    self: str
    research_search: str
    review_queue: str
    governance: str


class ResearchAnswerResponse(BaseModel):
    answer_id: str
    research_run_id: str
    retrieval_run_id: str
    version: int
    status: str
    answer_summary: str
    uncertainty: str | None = None
    contradictions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    claims: list[AnswerClaimItem] = Field(default_factory=list)
    model_provider_id: str
    model_id: str
    prompt_version: str
    policy_version: str
    retrieval_index_id: str | None = None
    index_manifest_checksum: str | None = None
    evidence_context_sha256: str
    created_at: str | None = None
    links: AnswerVersionLinks


class ProviderHealthItem(BaseModel):
    provider_id: str
    status: str
    checked_at: str
    latency_ms: int | None = None
    safe_code: str | None = None


class ModelGatewayOverviewResponse(BaseModel):
    metrics: dict[str, object]
    active_policy_version: int | None = None
    active_prompt_count: int
    evaluation_status: str


class ModelPolicySummary(BaseModel):
    policy_id: str
    version_number: int
    status: str
    allowed_providers: list[str]
    allowed_models: list[str]
    use_cases: list[str]
    sha256: str
    approved_by: str | None = None
    approved_at: str | None = None


class ModelPolicyListResponse(BaseModel):
    items: list[ModelPolicySummary]


class PromptTemplateSummary(BaseModel):
    template_id: str
    name: str
    use_case: str
    version: int
    status: str
    sha256: str
    approved_by: str | None = None
    approved_at: str | None = None
    evaluation_status: str


class PromptTemplateListResponse(BaseModel):
    items: list[PromptTemplateSummary]


class ActivatePolicyRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    approved_evaluation_id: str = Field(min_length=3, max_length=128)


class ActivatePromptRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    approved_evaluation_id: str = Field(min_length=3, max_length=128)


class ActivationResponse(BaseModel):
    resource_id: str
    status: str
    approved_evaluation_id: str
