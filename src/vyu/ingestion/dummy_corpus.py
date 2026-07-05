from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.vyu.contracts import (
    DocumentRecord,
    EvidenceProfile,
    GoldenQuestion,
    LoadedCorpus,
    PassageRecord,
    StudyDesign,
)


def load_dummy_corpus(root: Path) -> LoadedCorpus:
    article_root = root / "data" / "dummy_articles"
    question_root = root / "data" / "golden_questions"

    documents = {
        item["document_id"]: _document_from_json(item)
        for item in _read_jsonl(article_root / "documents.jsonl")
    }
    passages = {
        item["passage_id"]: _passage_from_json(item)
        for item in _read_jsonl(article_root / "passages.jsonl")
    }
    evidence_profiles = {
        item["document_id"]: _evidence_from_json(item)
        for item in _read_jsonl(article_root / "evidence_ground_truth.jsonl")
    }
    retracted_document_ids = {
        item["document_id"]
        for item in _read_jsonl(article_root / "retraction_ground_truth.jsonl")
    }
    golden_questions = {
        item["question_id"]: GoldenQuestion(**item)
        for item in _read_jsonl(question_root / "questions.jsonl")
    }
    expected_documents = {
        item["question_id"]: list(item["document_ids"])
        for item in _read_jsonl(question_root / "expected_documents.jsonl")
    }
    expected_citations = {
        item["question_id"]: list(item["citation_ids"])
        for item in _read_jsonl(question_root / "expected_citations.jsonl")
    }
    expected_evidence_flags = {
        item["question_id"]: list(item["flags"])
        for item in _read_jsonl(question_root / "expected_evidence_flags.jsonl")
    }

    _validate_links(
        documents,
        passages,
        evidence_profiles,
        retracted_document_ids,
        golden_questions,
        expected_documents,
        expected_citations,
        expected_evidence_flags,
    )

    return LoadedCorpus(
        documents=documents,
        passages=passages,
        evidence_profiles=evidence_profiles,
        retracted_document_ids=retracted_document_ids,
        golden_questions=golden_questions,
        expected_documents=expected_documents,
        expected_citations=expected_citations,
        expected_evidence_flags=expected_evidence_flags,
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing required corpus file: {path}")
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _document_from_json(item: dict[str, Any]) -> DocumentRecord:
    return DocumentRecord(
        document_id=item["document_id"],
        title=item["title"],
        year=int(item["year"]),
        study_design=StudyDesign(item["study_design"]),
        source_type=item["source_type"],
        publication_status=item["publication_status"],
        abstract=item.get("abstract", ""),
        authors=tuple(item.get("authors", [])),
        journal=item.get("journal", "Vyu Synthetic Biomedical Corpus"),
        doi=item.get("doi"),
        pmid=item.get("pmid"),
        is_preprint=bool(item.get("is_preprint", False)),
        is_retracted=bool(item.get("is_retracted", False)),
        funding=item.get("funding"),
        conflicts=item.get("conflicts"),
        population=item.get("population"),
        intervention=item.get("intervention"),
        comparator=item.get("comparator"),
        outcomes=tuple(item.get("outcomes", [])),
    )


def _passage_from_json(item: dict[str, Any]) -> PassageRecord:
    return PassageRecord(
        passage_id=item["passage_id"],
        document_id=item["document_id"],
        section=item["section"],
        text=item["text"],
        page=item.get("page"),
        table_id=item.get("table_id"),
    )


def _evidence_from_json(item: dict[str, Any]) -> EvidenceProfile:
    return EvidenceProfile(
        document_id=item["document_id"],
        study_design=StudyDesign(item["study_design"]),
        evidence_level=item["evidence_level"],
        bias_flags=list(item.get("bias_flags", [])),
        applicability_flags=list(item.get("applicability_flags", [])),
        retraction_status=item["retraction_status"],
        preprint_status=bool(item["preprint_status"]),
        assessment_confidence=float(item["assessment_confidence"]),
        funding=item.get("funding"),
        conflicts=item.get("conflicts"),
        missing_information_warnings=list(item.get("missing_information_warnings", [])),
    )


def _validate_links(
    documents: dict[str, DocumentRecord],
    passages: dict[str, PassageRecord],
    evidence_profiles: dict[str, EvidenceProfile],
    retracted_document_ids: set[str],
    golden_questions: dict[str, GoldenQuestion],
    expected_documents: dict[str, list[str]],
    expected_citations: dict[str, list[str]],
    expected_evidence_flags: dict[str, list[str]],
) -> None:
    document_ids = set(documents)

    for passage in passages.values():
        if passage.document_id not in document_ids:
            raise ValueError(f"Passage {passage.passage_id} references unknown document.")

    for document_id in evidence_profiles:
        if document_id not in document_ids:
            raise ValueError(f"Evidence profile references unknown document {document_id}.")

    for document_id in retracted_document_ids:
        if document_id not in document_ids:
            raise ValueError(f"Retraction record references unknown document {document_id}.")
        if not documents[document_id].is_retracted:
            raise ValueError(f"Retraction record does not match document status {document_id}.")

    for question_id, docs in expected_documents.items():
        if question_id not in golden_questions:
            raise ValueError(f"Expected documents reference unknown question {question_id}.")
        missing = set(docs) - document_ids
        if missing:
            raise ValueError(f"Question {question_id} references unknown documents: {sorted(missing)}")

    for mapping_name, mapping in (
        ("expected citations", expected_citations),
        ("expected evidence flags", expected_evidence_flags),
    ):
        missing_questions = set(mapping) - set(golden_questions)
        if missing_questions:
            raise ValueError(
                f"{mapping_name} reference unknown questions: {sorted(missing_questions)}"
            )
