from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from src.vyu.ingestion.contracts import PhiStatus

CLASSIFIER_NAME = "vyu_rules_phi_classifier"
CLASSIFIER_VERSION = "1.0.0"
DEFINITION_TIMESTAMP = "2026-07-07T00:00:00Z"

_MRN_PATTERN = re.compile(r"\b(?:mrn|medical record(?: number)?)\s*[:#-]?\s*\d{4,}\b", re.I)
_PATIENT_ID_PATTERN = re.compile(
    r"\bpatient\s+(?:id|identifier|name)\s*[:#-]?\s*[A-Za-z0-9-]{3,}\b",
    re.I,
)
_DOB_PATTERN = re.compile(
    r"\b(?:date of birth|dob)\s*[:#-]?\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
    re.I,
)
_CONTACT_PATTERN = re.compile(r"\b(?:phone|email)\s*[:#-]?\s*[\w.+-]+@[\w.-]+\b", re.I)
_CLINICAL_NOTE_PATTERN = re.compile(
    r"\b(?:chief complaint|history of present illness|assessment and plan)\s*:",
    re.I,
)
_AMBIGUOUS_PATTERN = re.compile(r"\b(?:patient|clinical)\b", re.I)


@dataclass(frozen=True)
class ClassificationResult:
    status: PhiStatus
    classifier_name: str
    classifier_version: str
    definition_timestamp: str
    content_hash: str
    finding_categories: tuple[str, ...] = ()


class SensitiveDataClassifier(Protocol):
    def classify(self, text_sample: str, metadata: Mapping[str, str]) -> ClassificationResult: ...


def text_sample_hash(text_sample: str) -> str:
    return hashlib.sha256(text_sample.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RulesSensitiveDataClassifier:
    classifier_name: str = CLASSIFIER_NAME
    classifier_version: str = CLASSIFIER_VERSION
    definition_timestamp: str = DEFINITION_TIMESTAMP
    max_sample_chars: int = 64_000

    def classify(self, text_sample: str, metadata: Mapping[str, str]) -> ClassificationResult:
        del metadata
        normalized = text_sample[: self.max_sample_chars]
        content_hash = text_sample_hash(normalized)
        if not normalized.strip():
            return ClassificationResult(
                status=PhiStatus.UNKNOWN,
                classifier_name=self.classifier_name,
                classifier_version=self.classifier_version,
                definition_timestamp=self.definition_timestamp,
                content_hash=content_hash,
                finding_categories=("empty_sample",),
            )

        categories: list[str] = []
        if _MRN_PATTERN.search(normalized):
            categories.append("medical_record_number")
        if _PATIENT_ID_PATTERN.search(normalized):
            categories.append("patient_identifier")
        if _DOB_PATTERN.search(normalized):
            categories.append("patient_date_label")
        if _CONTACT_PATTERN.search(normalized):
            categories.append("contact_identifier")
        if _CLINICAL_NOTE_PATTERN.search(normalized):
            categories.append("clinical_note_structure")

        if categories:
            return ClassificationResult(
                status=PhiStatus.SUSPECTED_PHI,
                classifier_name=self.classifier_name,
                classifier_version=self.classifier_version,
                definition_timestamp=self.definition_timestamp,
                content_hash=content_hash,
                finding_categories=tuple(categories),
            )

        if _AMBIGUOUS_PATTERN.search(normalized):
            return ClassificationResult(
                status=PhiStatus.UNKNOWN,
                classifier_name=self.classifier_name,
                classifier_version=self.classifier_version,
                definition_timestamp=self.definition_timestamp,
                content_hash=content_hash,
                finding_categories=("ambiguous_clinical_language",),
            )

        return ClassificationResult(
            status=PhiStatus.NON_PHI,
            classifier_name=self.classifier_name,
            classifier_version=self.classifier_version,
            definition_timestamp=self.definition_timestamp,
            content_hash=content_hash,
        )


@dataclass
class RecordingSensitiveDataClassifier:
    classifier_name: str = CLASSIFIER_NAME
    classifier_version: str = CLASSIFIER_VERSION
    definition_timestamp: str = DEFINITION_TIMESTAMP
    forced_result: ClassificationResult | None = None
    calls: int = 0

    def classify(self, text_sample: str, metadata: Mapping[str, str]) -> ClassificationResult:
        self.calls += 1
        if self.forced_result is not None:
            return self.forced_result
        return RulesSensitiveDataClassifier(
            classifier_name=self.classifier_name,
            classifier_version=self.classifier_version,
            definition_timestamp=self.definition_timestamp,
        ).classify(text_sample, metadata)
