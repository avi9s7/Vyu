from __future__ import annotations

from src.vyu.synthesis.contracts import (
    ABSTENTION_REASON_CODES,
    ANSWER_STATUSES,
    CLAIM_SUPPORT_STATUSES,
    EVIDENCE_CONTEXT_BUILDER_VERSION,
    EVIDENCE_ITEM_BEGIN,
    EVIDENCE_ITEM_END,
    GROUNDED_ANSWER_PROMPT_NAME,
    GROUNDED_ANSWER_PROMPT_VERSION,
    GROUNDED_ANSWER_SCHEMA_VERSION,
    GROUNDED_SYNTHESIS_USE_CASE,
    MODEL_CALL_STATUSES,
    MODEL_POLICY_VERSION_STATUSES,
    PROMPT_TEMPLATE_STATUSES,
    UNTRUSTED_EVIDENCE_PREAMBLE,
)
from src.vyu.synthesis.context import (
    BuiltEvidenceContext,
    EvidenceContextBuilder,
    EvidenceContextItem,
    build_evidence_context,
)
from src.vyu.synthesis.handler import SynthesisHandler
from src.vyu.synthesis.prompt_config import (
    CANONICAL_GROUNDED_ANSWER_PROMPT_SHA256,
    GROUNDED_ANSWER_OUTPUT_JSON_SCHEMA,
    GROUNDED_ANSWER_SYSTEM_PROMPT,
    grounded_answer_prompt_bundle,
    grounded_answer_prompt_sha256,
    render_grounded_answer_user_prompt,
)
from src.vyu.synthesis.repository import (
    AnswerClaimDraft,
    AnswerRecord,
    ModelCallRecord,
    ModelPolicyRecord,
    ModelSynthesisRepository,
    PromptTemplateRecord,
)
from src.vyu.synthesis.schema import (
    GroundedAnswerClaimOutput,
    GroundedAnswerOutput,
    GroundedAnswerSemanticValidationError,
    parse_grounded_answer_output,
    validate_grounded_answer_semantics,
)

from src.vyu.synthesis.service import SynthesisExecutor, SynthesisExecutionResult, SynthesisSettings
from src.vyu.synthesis.validators import (
    SynthesisValidationResult,
    ValidationWarning,
    required_abstention_reason,
    validate_synthesis_output,
)

__all__ = [
    "ABSTENTION_REASON_CODES",
    "ANSWER_STATUSES",
    "BuiltEvidenceContext",
    "CANONICAL_GROUNDED_ANSWER_PROMPT_SHA256",
    "CLAIM_SUPPORT_STATUSES",
    "EVIDENCE_CONTEXT_BUILDER_VERSION",
    "EVIDENCE_ITEM_BEGIN",
    "EVIDENCE_ITEM_END",
    "GROUNDED_ANSWER_OUTPUT_JSON_SCHEMA",
    "GROUNDED_ANSWER_PROMPT_NAME",
    "GROUNDED_ANSWER_PROMPT_VERSION",
    "GROUNDED_ANSWER_SCHEMA_VERSION",
    "GROUNDED_ANSWER_SYSTEM_PROMPT",
    "GROUNDED_SYNTHESIS_USE_CASE",
    "SynthesisExecutionResult",
    "SynthesisExecutor",
    "SynthesisHandler",
    "SynthesisSettings",
    "SynthesisValidationResult",
    "EvidenceContextBuilder",
    "EvidenceContextItem",
    "GroundedAnswerClaimOutput",
    "GroundedAnswerOutput",
    "GroundedAnswerSemanticValidationError",
    "MODEL_CALL_STATUSES",
    "MODEL_POLICY_VERSION_STATUSES",
    "PROMPT_TEMPLATE_STATUSES",
    "UNTRUSTED_EVIDENCE_PREAMBLE",
    "build_evidence_context",
    "grounded_answer_prompt_bundle",
    "grounded_answer_prompt_sha256",
    "parse_grounded_answer_output",
    "render_grounded_answer_user_prompt",
    "validate_grounded_answer_semantics",
    "required_abstention_reason",
    "validate_synthesis_output",
    "ValidationWarning",
    "AnswerClaimDraft",
    "AnswerRecord",
    "ModelCallRecord",
    "ModelPolicyRecord",
    "ModelSynthesisRepository",
    "PromptTemplateRecord",
]
