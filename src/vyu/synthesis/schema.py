from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from src.vyu.synthesis.contracts import ABSTENTION_REASON_CODES


class GroundedAnswerClaimOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_text: str
    citation_ids: list[str]
    support: Literal["supported", "mixed", "unsupported"]

    @field_validator("claim_text")
    @classmethod
    def claim_text_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("claim_text must not be empty")
        return normalized

    @field_validator("citation_ids")
    @classmethod
    def citation_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        normalized = [citation_id.strip() for citation_id in value if citation_id.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("citation_ids must be unique")
        return normalized


class GroundedAnswerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer_summary: str
    claims: list[GroundedAnswerClaimOutput] = Field(default_factory=list)
    uncertainty: str = ""
    contradictions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    abstained: bool
    abstention_reason: str | None = None

    @field_validator("answer_summary")
    @classmethod
    def answer_summary_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("answer_summary must not be empty")
        return normalized

    @field_validator("abstention_reason")
    @classmethod
    def abstention_reason_must_be_known(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if normalized not in ABSTENTION_REASON_CODES:
            raise ValueError(f"unknown abstention_reason: {normalized}")
        return normalized

    @model_validator(mode="after")
    def abstention_fields_are_consistent(self) -> "GroundedAnswerOutput":
        if self.abstained:
            if self.abstention_reason is None:
                raise ValueError("abstention_reason is required when abstained is true")
            if self.claims:
                raise ValueError("claims must be empty when abstained is true")
            return self
        if self.abstention_reason is not None:
            raise ValueError("abstention_reason must be null when abstained is false")
        return self


class GroundedAnswerSemanticValidationError(ValueError):
    def __init__(self, errors: tuple[str, ...]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def parse_grounded_answer_output(payload: object) -> GroundedAnswerOutput:
    try:
        return GroundedAnswerOutput.model_validate(payload)
    except ValidationError as exc:
        raise GroundedAnswerSemanticValidationError(
            tuple(error["msg"] for error in exc.errors())
        ) from exc


def validate_grounded_answer_semantics(
    output: GroundedAnswerOutput,
    *,
    allowed_citation_ids: frozenset[str],
) -> None:
    errors: list[str] = []

    for index, claim in enumerate(output.claims, start=1):
        if not claim.citation_ids:
            errors.append(f"claim {index} is missing citation_ids")
            continue
        unknown = sorted(
            citation_id
            for citation_id in claim.citation_ids
            if citation_id not in allowed_citation_ids
        )
        if unknown:
            errors.append(f"claim {index} cites unknown citation_ids: {', '.join(unknown)}")
        if claim.support in {"supported", "mixed"} and not claim.citation_ids:
            errors.append(f"claim {index} requires at least one citation")

    summary_normalized = _normalize_text(output.answer_summary)
    for index, claim in enumerate(output.claims, start=1):
        if claim.support != "unsupported":
            continue
        claim_normalized = _normalize_text(claim.claim_text)
        if claim_normalized and claim_normalized in summary_normalized:
            errors.append(
                f"unsupported claim {index} appears as a fact in answer_summary"
            )

    if errors:
        raise GroundedAnswerSemanticValidationError(tuple(errors))


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().split())
