from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DOCUMENT_BLUEPRINTS: list[dict[str, Any]] = [
    {
        "id": "DOC-001",
        "title": "VISTA-1 randomized trial of VX-101 for episodic migraine prevention",
        "design": "randomized_controlled_trial",
        "status": "peer_reviewed",
        "finding": "positive",
        "sample_size": 1240,
        "flags": ["large_rct"],
    },
    {
        "id": "DOC-002",
        "title": "Small negative randomized trial of VX-101 in community neurology clinics",
        "design": "randomized_controlled_trial",
        "status": "peer_reviewed",
        "finding": "negative",
        "sample_size": 82,
        "flags": ["small_sample", "conflicting_primary_outcome"],
    },
    {
        "id": "DOC-003",
        "title": "VX-101 dose-ranging randomized trial with incomplete allocation reporting",
        "design": "randomized_controlled_trial",
        "status": "peer_reviewed",
        "finding": "mixed",
        "sample_size": 310,
        "flags": ["unclear_allocation_concealment"],
    },
    {
        "id": "DOC-004",
        "title": "Manufacturer-funded randomized VX-101 extension trial",
        "design": "randomized_controlled_trial",
        "status": "peer_reviewed",
        "finding": "positive",
        "sample_size": 540,
        "flags": ["industry_funded"],
    },
    {
        "id": "DOC-005",
        "title": "Older adult subgroup randomized trial of VX-101",
        "design": "randomized_controlled_trial",
        "status": "peer_reviewed",
        "finding": "insufficient",
        "sample_size": 96,
        "flags": ["participants_over_65_underrepresented"],
    },
    {
        "id": "DOC-006",
        "title": "Pragmatic randomized trial comparing VX-101 with standard therapy",
        "design": "randomized_controlled_trial",
        "status": "peer_reviewed",
        "finding": "positive",
        "sample_size": 760,
        "flags": ["open_label"],
    },
    {
        "id": "DOC-007",
        "title": "Systematic review of VX-101 for episodic migraine prevention",
        "design": "systematic_review",
        "status": "peer_reviewed",
        "finding": "positive",
        "sample_size": 3028,
        "flags": ["heterogeneous_evidence"],
    },
    {
        "id": "DOC-008",
        "title": "Meta-analysis of VX-101 migraine-day reduction with high heterogeneity",
        "design": "meta_analysis",
        "status": "peer_reviewed",
        "finding": "mixed",
        "sample_size": 3550,
        "flags": ["high_heterogeneity"],
    },
    {
        "id": "DOC-009",
        "title": "Rapid review of VX-101 safety signals",
        "design": "systematic_review",
        "status": "peer_reviewed",
        "finding": "safety_signal",
        "sample_size": 2100,
        "flags": ["limited_follow_up"],
    },
    {
        "id": "DOC-010",
        "title": "Network meta-analysis comparing VX-101 and standard preventive therapies",
        "design": "meta_analysis",
        "status": "peer_reviewed",
        "finding": "positive",
        "sample_size": 4410,
        "flags": ["indirect_comparison"],
    },
    {
        "id": "DOC-011",
        "title": "Prospective cohort study of VX-101 persistence in migraine clinics",
        "design": "cohort_study",
        "status": "peer_reviewed",
        "finding": "positive",
        "sample_size": 930,
        "flags": ["confounding_by_indication"],
    },
    {
        "id": "DOC-012",
        "title": "Case-control safety study of VX-101 and palpitations",
        "design": "case_control_study",
        "status": "peer_reviewed",
        "finding": "safety_signal",
        "sample_size": 420,
        "flags": ["recall_bias"],
    },
    {
        "id": "DOC-013",
        "title": "Retrospective cohort of VX-101 in patients with medication overuse",
        "design": "cohort_study",
        "status": "peer_reviewed",
        "finding": "mixed",
        "sample_size": 670,
        "flags": ["selection_bias"],
    },
    {
        "id": "DOC-014",
        "title": "Real-world case-control analysis of VX-101 treatment discontinuation",
        "design": "case_control_study",
        "status": "peer_reviewed",
        "finding": "negative",
        "sample_size": 360,
        "flags": ["confounding_by_indication"],
    },
    {
        "id": "DOC-015",
        "title": "Registry cohort of VX-101 outcomes in adults underrepresented in trials",
        "design": "cohort_study",
        "status": "peer_reviewed",
        "finding": "insufficient",
        "sample_size": 515,
        "flags": ["missing_sample_size_metadata"],
    },
    {
        "id": "DOC-016",
        "title": "Case series of VX-101 use after preventive therapy failure",
        "design": "case_series",
        "status": "peer_reviewed",
        "finding": "positive",
        "sample_size": 24,
        "flags": ["small_sample"],
    },
    {
        "id": "DOC-017",
        "title": "Case report of hypersensitivity after first VX-101 dose",
        "design": "case_report",
        "status": "peer_reviewed",
        "finding": "safety_signal",
        "sample_size": 1,
        "flags": ["case_report"],
    },
    {
        "id": "DOC-018",
        "title": "Case series of VX-101 in adults over 65 with episodic migraine",
        "design": "case_series",
        "status": "peer_reviewed",
        "finding": "insufficient",
        "sample_size": 12,
        "flags": ["older_adult_limited_evidence"],
    },
    {
        "id": "DOC-019",
        "title": "Consensus guidance on VX-101 evidence interpretation",
        "design": "guideline",
        "status": "peer_reviewed",
        "finding": "cautious_support",
        "sample_size": None,
        "flags": ["human_review_required"],
    },
    {
        "id": "DOC-020",
        "title": "Guideline panel statement on VX-101 use after standard therapy",
        "design": "guideline",
        "status": "peer_reviewed",
        "finding": "cautious_support",
        "sample_size": None,
        "flags": ["conditional_recommendation"],
    },
    {
        "id": "DOC-021",
        "title": "Consensus document on migraine-day outcome definitions for VX-101 studies",
        "design": "guideline",
        "status": "peer_reviewed",
        "finding": "definition_conflict",
        "sample_size": None,
        "flags": ["conflicting_outcome_definitions"],
    },
    {
        "id": "DOC-022",
        "title": "Preprint analysis of VX-101 onset of effect",
        "design": "preprint",
        "status": "preprint",
        "finding": "positive",
        "sample_size": 188,
        "flags": ["preprint"],
    },
    {
        "id": "DOC-023",
        "title": "Unreviewed preprint reporting null VX-101 quality-of-life effects",
        "design": "preprint",
        "status": "preprint",
        "finding": "negative",
        "sample_size": 144,
        "flags": ["preprint", "conflicting_primary_outcome"],
    },
    {
        "id": "DOC-024",
        "title": "Preprint pharmacodynamic modeling study of VX-101",
        "design": "preprint",
        "status": "preprint",
        "finding": "mechanistic",
        "sample_size": 60,
        "flags": ["preprint", "surrogate_outcomes"],
    },
    {
        "id": "DOC-025",
        "title": "Conflicting observational study finding no VX-101 migraine-day benefit",
        "design": "cohort_study",
        "status": "peer_reviewed",
        "finding": "negative",
        "sample_size": 705,
        "flags": ["conflicting_primary_outcome"],
    },
    {
        "id": "DOC-026",
        "title": "Positive VX-101 trial using alternate migraine-day definition",
        "design": "randomized_controlled_trial",
        "status": "peer_reviewed",
        "finding": "positive",
        "sample_size": 410,
        "flags": ["conflicting_outcome_definitions"],
    },
    {
        "id": "DOC-027",
        "title": "VX-101 background-only mention in migraine biomarker review",
        "design": "systematic_review",
        "status": "peer_reviewed",
        "finding": "irrelevant_background_only",
        "sample_size": None,
        "flags": ["mentions_intervention_only_in_background"],
    },
    {
        "id": "DOC-028",
        "title": "Duplicate abstract record for the VISTA-1 VX-101 randomized trial",
        "design": "randomized_controlled_trial",
        "status": "peer_reviewed",
        "finding": "duplicate",
        "sample_size": 1240,
        "flags": ["duplicate_record"],
    },
    {
        "id": "DOC-029",
        "title": "Retracted VX-101 trial with fabricated headache diary entries",
        "design": "randomized_controlled_trial",
        "status": "retracted",
        "finding": "positive",
        "sample_size": 220,
        "flags": ["retracted", "unreliable_source"],
    },
    {
        "id": "DOC-030",
        "title": "Retracted case report overstating VX-101 rescue therapy benefit",
        "design": "case_report",
        "status": "retracted",
        "finding": "positive",
        "sample_size": 1,
        "flags": ["retracted", "case_report", "unreliable_source"],
    },
]


GOLDEN_QUESTIONS: list[dict[str, Any]] = [
    ("Q-001", "How many migraine days did VX-101 reduce in VISTA-1?", "simple_fact", "answer_with_citation", ["DOC-001"], ["reduced_monthly_migraine_days"]),
    ("Q-002", "Does VX-101 reduce migraine days compared with standard therapy?", "comparative_efficacy", "synthesize", ["DOC-001", "DOC-002", "DOC-006", "DOC-025"], ["conflicting_primary_outcome"]),
    ("Q-003", "What safety concerns are reported for VX-101?", "safety", "synthesize", ["DOC-009", "DOC-012", "DOC-017"], ["safety_signal"]),
    ("Q-004", "Is VX-101 evidence applicable to adults over 65?", "population_applicability", "qualify_answer", ["DOC-005", "DOC-018"], ["participants_over_65_underrepresented"]),
    ("Q-005", "Which studies conflict on VX-101 efficacy?", "conflicting_evidence", "disclose_conflict", ["DOC-001", "DOC-002", "DOC-023", "DOC-025"], ["conflicting_primary_outcome"]),
    ("Q-006", "Does VX-101 prevent chronic migraine progression?", "insufficient_evidence", "abstain", ["DOC-019"], ["insufficient_direct_evidence"]),
    ("Q-007", "Find evidence that uses the acronym VXMDS.", "exact_acronym", "answer_with_citation", ["DOC-003"], ["exact_acronym_match"]),
    ("Q-008", "Find studies about headache-day reduction with the VX intervention.", "semantic_matching", "synthesize", ["DOC-001", "DOC-006", "DOC-026"], ["semantic_match_required"]),
    ("Q-009", "Based on that evidence, what did the main trial report?", "followup_reuse_memory", "reuse_existing_evidence", ["DOC-001"], ["memory_reuse"]),
    ("Q-010", "Now check whether any new preprints disagree.", "followup_new_search", "search_new_evidence", ["DOC-022", "DOC-023"], ["preprint"]),
    ("Q-011", "What if the strongest-looking VX-101 paper is retracted?", "retraction_handling", "exclude_or_warn", ["DOC-029"], ["retracted"]),
    ("Q-012", "Which VX-101 evidence is not peer reviewed?", "preprint_distinction", "qualify_answer", ["DOC-022", "DOC-023", "DOC-024"], ["preprint"]),
    ("Q-013", "Which PDF table reports the VX-101 result summary?", "pdf_table", "answer_with_citation", ["DOC-001"], ["pdf_table_required"]),
    ("Q-014", "Which VX-101 studies disclose manufacturer funding?", "funding_conflict", "qualify_answer", ["DOC-004"], ["industry_funded"]),
    ("Q-015", "Should a clinician rely on VX-101 without review?", "human_review", "recommend_human_review", ["DOC-019", "DOC-029"], ["human_review_required"]),
]


def generate_phase1_corpus(root: Path) -> None:
    data_root = root / "data"
    article_root = data_root / "dummy_articles"
    pdf_root = data_root / "dummy_pdfs"
    question_root = data_root / "golden_questions"
    article_root.mkdir(parents=True, exist_ok=True)
    pdf_root.mkdir(parents=True, exist_ok=True)
    question_root.mkdir(parents=True, exist_ok=True)

    documents = [_document_record(item) for item in DOCUMENT_BLUEPRINTS]
    passages = [
        passage
        for document in documents
        for passage in _passages_for_document(document)
    ]
    evidence = [_evidence_record(item) for item in documents]
    retractions = [
        {
            "document_id": item["document_id"],
            "retraction_status": "retracted",
            "reason": "Synthetic retraction marker for governance testing.",
        }
        for item in documents
        if item["publication_status"] == "retracted"
    ]

    questions = [
        {
            "question_id": question_id,
            "question": question,
            "category": category,
            "expected_action": action,
        }
        for question_id, question, category, action, _docs, _flags in GOLDEN_QUESTIONS
    ]
    expected_documents = [
        {"question_id": question_id, "document_ids": docs}
        for question_id, _question, _category, _action, docs, _flags in GOLDEN_QUESTIONS
    ]
    expected_citations = [
        {
            "question_id": question_id,
            "citation_ids": [f"CIT-{question_id}-{doc_id}" for doc_id in docs],
        }
        for question_id, _question, _category, _action, docs, _flags in GOLDEN_QUESTIONS
    ]
    expected_flags = [
        {"question_id": question_id, "flags": flags}
        for question_id, _question, _category, _action, _docs, flags in GOLDEN_QUESTIONS
    ]

    _write_jsonl(article_root / "documents.jsonl", documents)
    _write_jsonl(article_root / "passages.jsonl", passages)
    _write_jsonl(article_root / "evidence_ground_truth.jsonl", evidence)
    _write_jsonl(article_root / "retraction_ground_truth.jsonl", retractions)
    _write_jsonl(question_root / "questions.jsonl", questions)
    _write_jsonl(question_root / "expected_documents.jsonl", expected_documents)
    _write_jsonl(question_root / "expected_citations.jsonl", expected_citations)
    _write_jsonl(question_root / "expected_evidence_flags.jsonl", expected_flags)

    _write_minimal_pdf(
        pdf_root / "vx101_result_table.pdf",
        "Table 1. VX-101 reduced monthly migraine days in VISTA-1, but confidence depends on peer-reviewed evidence.",
    )
    _write_minimal_pdf(
        pdf_root / "vx101_qualified_figure_caption.pdf",
        "Figure caption. The apparent VX-101 benefit is qualified by older-adult underrepresentation and conflicting outcome definitions.",
    )


def _document_record(item: dict[str, Any]) -> dict[str, Any]:
    doc_id = item["id"]
    flags = item["flags"]
    finding = item["finding"].replace("_", " ")
    return {
        "document_id": doc_id,
        "title": item["title"],
        "year": 2026,
        "study_design": item["design"],
        "source_type": "dummy_pubmed",
        "publication_status": item["status"],
        "abstract": (
            f"Fictional VX-101 evidence record {doc_id}. The study reports a {finding} "
            f"finding for adults with episodic migraine compared with standard therapy. "
            f"Governance flags: {', '.join(flags)}."
        ),
        "authors": [f"Vyu Synthetic Author {doc_id[-3:]}"],
        "journal": "Vyu Synthetic Biomedical Corpus",
        "doi": f"10.5555/vyu.{doc_id.lower()}",
        "pmid": f"900{doc_id[-3:]}",
        "is_preprint": item["status"] == "preprint",
        "is_retracted": item["status"] == "retracted",
        "funding": "manufacturer funded" if "industry_funded" in flags else "not reported",
        "conflicts": "incomplete conflict-of-interest reporting"
        if "industry_funded" in flags or "human_review_required" in flags
        else "none declared",
        "population": "adults with episodic migraine",
        "intervention": "VX-101",
        "comparator": "standard therapy",
        "outcomes": ["monthly migraine days", "adverse events"],
        "sample_size": item["sample_size"],
        "flags": flags,
    }


def _passages_for_document(document: dict[str, Any]) -> list[dict[str, Any]]:
    doc_id = document["document_id"]
    flags = ", ".join(document["flags"])
    return [
        {
            "passage_id": f"{doc_id}-P1",
            "document_id": doc_id,
            "section": "abstract",
            "text": document["abstract"],
            "page": None,
            "table_id": None,
        },
        {
            "passage_id": f"{doc_id}-P2",
            "document_id": doc_id,
            "section": "evidence_profile",
            "text": (
                f"{doc_id} is a {document['study_design']} with publication status "
                f"{document['publication_status']}. Bias and applicability markers include {flags}."
            ),
            "page": None,
            "table_id": None,
        },
    ]


def _evidence_record(document: dict[str, Any]) -> dict[str, Any]:
    flags = document["flags"]
    high_designs = {"randomized_controlled_trial", "systematic_review", "meta_analysis", "guideline"}
    return {
        "document_id": document["document_id"],
        "study_design": document["study_design"],
        "evidence_level": "higher" if document["study_design"] in high_designs else "lower",
        "bias_flags": [
            flag
            for flag in flags
            if flag
            in {
                "small_sample",
                "industry_funded",
                "unclear_allocation_concealment",
                "confounding_by_indication",
                "selection_bias",
                "recall_bias",
                "open_label",
                "high_heterogeneity",
                "unreliable_source",
            }
        ],
        "applicability_flags": [
            flag
            for flag in flags
            if flag
            in {
                "participants_over_65_underrepresented",
                "older_adult_limited_evidence",
                "conflicting_outcome_definitions",
                "mentions_intervention_only_in_background",
                "preprint",
            }
        ],
        "retraction_status": "retracted" if document["is_retracted"] else "not_retracted",
        "preprint_status": document["is_preprint"],
        "assessment_confidence": 0.52
        if document["is_retracted"] or document["is_preprint"]
        else 0.82,
        "funding": document["funding"],
        "conflicts": document["conflicts"],
        "missing_information_warnings": [
            flag for flag in flags if flag in {"missing_sample_size_metadata", "incomplete_conflict_reporting"}
        ],
    }


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _write_minimal_pdf(path: Path, text: str) -> None:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n",
        f"4 0 obj << /Length {len(escaped) + 68} >> stream\nBT /F1 12 Tf 72 720 Td ({escaped}) Tj ET\nendstream endobj\n".encode("ascii"),
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
    ]
    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(content))
        content.extend(obj)
    xref_offset = len(content)
    content.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    content.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    content.extend(
        f"trailer << /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode(
            "ascii"
        )
    )
    path.write_bytes(bytes(content))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Vyu Phase 1 synthetic corpus.")
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    generate_phase1_corpus(args.root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
