# Vyu POC: Upstream Code Reuse, Modification, Dummy Pipeline, and Test Plan

> **Status:** Planning document  
> **Last reviewed:** 13 June 2026  
> **Scope:** Functional proof of concept. Scalability, high concurrency, production hardening, and full clinical validation are intentionally out of scope.

## 1. Purpose

This document defines a practical plan for building a Vyu proof of concept by evaluating and selectively adapting code and design patterns from the following open-source projects:

- `GoogleCloudPlatform/LifeSciences` — BioCompass on Gemini Enterprise
- `GoogleCloudPlatform/hcls-mcp-servers` — PubMed MCP server
- `gzxiong/MedRAG`
- `Zaoqu-Liu/PubMedRAG`
- `RAG-Gym/RAG-Gym`
- `HamsiniGupta/PubMedRAG`, if this was the intended repository referred to as “Google PubMedRAG”

Vyu is envisioned as a governed healthcare AI research platform providing:

- Citation-grounded answers
- Evidence grading and evidence-quality assessment
- Bias and applicability assessment
- Research memory
- Guided literature deep-dives
- Explainable Trust Score
- Governance Box and auditability
- Policy, evidence-brief, and research-output generation

The recommended approach is **not** to merge entire upstream repositories. Instead, Vyu should use them as modular references and selectively reuse clearly licensed components behind Vyu-owned interfaces.

---

## 2. Executive Recommendation

Use the repositories as **reference implementations and modular upstreams**, not as one combined application.

The strongest POC foundation is:

1. **Google BioCompass and PubMed MCP** for PubMed/PMC connectivity, multi-source research orchestration, entity extraction, deep-research workflows, critic loops, and research-methodology skills.
2. **gzxiong/MedRAG** for retriever experimentation, especially MedCPT, BM25, FAISS, HNSW, and reciprocal-rank fusion.
3. A **new Vyu evidence, governance, memory, citation, and audit layer** implemented around stable internal contracts.
4. **Zaoqu-Liu/PubMedRAG** as a functional reference for question-driven PubMed search, citations, and session reuse, but not copied into a proprietary service without GPL review.
5. **RAG-Gym** as a later experimental track for optimizing iterative, agentic literature searches—not as a dependency for the first POC.

No clearly identifiable official repository named **Google PubMedRAG** was found. The closest verified Google implementations are:

- `GoogleCloudPlatform/hcls-mcp-servers/pubmed_mcp`
- `GoogleCloudPlatform/LifeSciences/.../biocompass-on-gemini-enterprise`

These should be treated as the likely Google-origin upstreams unless a different exact repository URL is supplied.

---

## 3. Suitability Summary

| Repository | Best Contribution to Vyu | Suitability | Recommendation | Main Concerns |
|---|---|---:|---|---|
| Google BioCompass | Multi-source research orchestration, critic loop, research skills, uploaded-file handling | Very high | Reuse selected architecture and Apache-licensed components | Coupled to Google ADK, Vertex AI, Gemini Enterprise, and specific models |
| Google PubMed MCP | PubMed, PMC, PubTator, citation graph, and entity connectors | Very high | Adapt API clients into Vyu connectors | MCP and optional BigQuery assumptions; not a complete evidence platform |
| gzxiong/MedRAG | MedCPT, BM25, FAISS, HNSW, RRF, medical retrieval experiments | High for retrieval | Reuse selected public-domain code and retrieval concepts | Research-oriented; large automatic downloads; shell commands; older dependency patterns |
| Zaoqu-Liu/PubMedRAG | Question-driven PubMed search, citation formatting, follow-up search, session cache | Medium–high conceptually | Reference or isolate after licence review | GPL-3.0; monolithic structure; abstract-heavy; direct provider coupling |
| RAG-Gym/RAG-Gym | Iterative search agents and process-supervised RAG optimization | Low for first POC; potentially high later | Evaluate only after a stable Vyu baseline | No clearly verified root licence during review; training complexity |
| HamsiniGupta/PubMedRAG | PubMedQA/SimCSE biomedical retriever experiment | Low–medium | Use as benchmark inspiration only | No clearly verified licence; training experiment rather than application platform |

---

## 4. Why BioCompass Is the Closest Starting Point

BioCompass is the closest verified upstream to Vyu’s functional vision because it already contains patterns for:

- Fast PubMed lookup
- Biomedical entity and relationship extraction
- Parallel retrieval from:
  - PubMed
  - Europe PMC
  - bioRxiv/medRxiv
  - ClinicalTrials.gov
- Citation-grounded evidence synthesis
- Critic-driven revision loops
- Uploaded PDF/image handoff
- PICO search strategy
- PRISMA-style review workflows
- Safety-signal scans
- Competitive-landscape scans
- Methodological critique and groundedness evaluations

It should be used primarily as an **orchestration and workflow reference**. Vyu should avoid hard-coding its own core domain logic to Google ADK or Gemini Enterprise.

---

## 5. Why MedRAG Remains Important

MedRAG is best treated as a **retrieval laboratory**.

It supports representative retrieval configurations over medical corpora:

- BM25 for lexical retrieval
- Contriever for general semantic retrieval
- SPECTER for scientific-document retrieval
- MedCPT for biomedical retrieval
- Reciprocal-rank fusion across multiple retrievers
- FAISS dense indexes
- Optional HNSW acceleration
- Iterative follow-up querying through i-MedRAG

For Vyu, the most useful initial experiment is:

```text
BM25 + MedCPT + Reciprocal Rank Fusion + optional reranking
```

MedRAG should not become Vyu’s application architecture. Its retrieval code should be isolated behind Vyu interfaces.

---

## 6. Why RAG-Gym Should Be Deferred

RAG-Gym focuses on agentic RAG optimization using techniques such as:

- Search/reasoning trajectories
- Supervised fine-tuning
- Direct preference optimization
- Process reward models
- Iterative information-seeking agents

These are valuable only after Vyu has:

- A stable retrieval baseline
- A fixed evaluation dataset
- Logged research trajectories
- Clear quality metrics
- Sufficient evidence that a deterministic guided workflow is inadequate

For the first POC, use a transparent state machine:

```text
Define question
    ↓
Generate subquestion
    ↓
Retrieve
    ↓
Assess evidence coverage
   ↙                    ↘
Enough evidence        Evidence gap
   ↓                       ↓
Synthesize             Generate next query
```

Every step must be logged for auditability.

---

## 7. Licence and Provenance Gate

Complete this gate before copying source files.

| Upstream | Observed Licence Status | POC Action |
|---|---|---|
| GoogleCloudPlatform/LifeSciences | Apache-2.0 repository licence | Suitable for selective reuse with notices and attribution |
| GoogleCloudPlatform/hcls-mcp-servers | Verify repository licence at intake | Reuse only after licence is captured in the manifest |
| gzxiong/MedRAG | US Government public-domain notice | Code is generally reusable; separately review models, corpora, and dependencies |
| Zaoqu-Liu/PubMedRAG | GPL-3.0 licence file | Reference only unless GPL use is approved |
| RAG-Gym/RAG-Gym | No root licence confirmed during review | Treat as reference-only until clarified |
| HamsiniGupta/PubMedRAG | No licence confirmed during review | Do not copy source until clarified |

### Important Licence Rules

- Repository code, models, datasets, embeddings, and external corpora may have different licences.
- A permissive code licence does not automatically cover downloaded PubMed, StatPearls, textbook, model, or embedding assets.
- Retain all mandatory copyright and licence notices.
- Record the exact upstream commit used.
- Record every upstream file copied or substantially adapted.
- Do not rely only on a README licence statement when a repository licence file conflicts with it.
- Obtain legal review before distributing a proprietary product containing or derived from GPL code.

This is an engineering plan, not legal advice.

---

## 8. Upstream Intake Manifest

Create `upstreams.yaml`:

```yaml
upstreams:
  google_biocompass:
    repo: GoogleCloudPlatform/LifeSciences
    path: applications/pharma-on-gemini-enterprise/biocompass-on-gemini-enterprise
    license: Apache-2.0
    usage: selected_components

  google_pubmed_mcp:
    repo: GoogleCloudPlatform/hcls-mcp-servers
    path: pubmed_mcp
    license: verify_at_intake
    usage: connector_reference

  medrag:
    repo: gzxiong/MedRAG
    license: US-Government-Public-Domain
    usage: retriever_adapter

  zaoqu_pubmedrag:
    repo: Zaoqu-Liu/PubMedRAG
    license: GPL-3.0
    usage: reference_only

  rag_gym:
    repo: RAG-Gym/RAG-Gym
    license: unverified
    usage: reference_only

  pubmedrag_simcse:
    repo: HamsiniGupta/PubMedRAG
    license: unverified
    usage: reference_only
```

For each upstream, record:

- Clone URL
- Default branch
- Exact commit SHA
- Repository licence
- Licence-file hash
- Reviewed files
- Copied or adapted files
- Local modifications
- Dependency licences
- Model licences
- Dataset/corpus licences
- Required attribution

---

## 9. Clone Repositories into a Read-Only Workspace

```bash
mkdir -p vyu-poc/upstreams
cd vyu-poc/upstreams

git clone --filter=blob:none \
  https://github.com/GoogleCloudPlatform/LifeSciences.git

git clone --filter=blob:none \
  https://github.com/GoogleCloudPlatform/hcls-mcp-servers.git

git clone --depth 1 \
  https://github.com/gzxiong/MedRAG.git

git clone --depth 1 \
  https://github.com/Zaoqu-Liu/PubMedRAG.git

git clone --depth 1 \
  https://github.com/RAG-Gym/RAG-Gym.git

git clone --depth 1 \
  https://github.com/HamsiniGupta/PubMedRAG.git \
  PubMedRAG-SimCSE
```

Pin the reviewed commits:

```bash
for repo in \
  LifeSciences \
  hcls-mcp-servers \
  MedRAG \
  PubMedRAG \
  RAG-Gym \
  PubMedRAG-SimCSE
do
  printf "%s: " "$repo"
  git -C "$repo" rev-parse HEAD
done > UPSTREAM_COMMITS.txt
```

Do not implement Vyu inside the upstream clones. Treat them as read-only source material.

---

## 10. Proposed Vyu POC Architecture

```text
                         ┌────────────────────────────┐
                         │        Vyu API/UI          │
                         └─────────────┬──────────────┘
                                       │
                         ┌─────────────▼──────────────┐
                         │ Research Workflow Manager  │
                         │ query plan / deep dive /   │
                         │ memory / report generation │
                         └──────┬─────────┬───────────┘
                                │         │
                 ┌──────────────▼─┐   ┌──▼────────────────┐
                 │ Source Adapters │   │ Uploaded Document │
                 │ PubMed / PMC /  │   │ Parsing Pipeline  │
                 │ trials/preprints│   │ PDF/text/tables   │
                 └────────┬────────┘   └────────┬──────────┘
                          │                     │
                    ┌─────▼─────────────────────▼─────┐
                    │ Normalized Evidence Repository  │
                    │ document, passage, study, claim │
                    │ citation and provenance records │
                    └──────────────┬──────────────────┘
                                   │
                  ┌────────────────▼────────────────┐
                  │ Retrieval and Reranking Layer   │
                  │ BM25 + MedCPT + RRF + filters   │
                  └────────────────┬────────────────┘
                                   │
                ┌──────────────────▼──────────────────┐
                │ Evidence Analysis Pipeline          │
                │ design / bias / conflicts /         │
                │ applicability / evidence profile    │
                └──────────────────┬──────────────────┘
                                   │
             ┌─────────────────────▼──────────────────────┐
             │ Grounded Answer and Report Generator       │
             │ claim-level citations and abstention       │
             └─────────────────────┬──────────────────────┘
                                   │
       ┌───────────────────────────▼──────────────────────────┐
       │ Trust Score + Governance Box + Immutable Audit Trace │
       └──────────────────────────────────────────────────────┘
```

---

## 11. Recommended POC Storage

Use simple local infrastructure first:

- **SQLite** for the smallest local demonstration, or **PostgreSQL** for a more realistic POC
- **FAISS** for dense vector search
- A small **BM25** index for lexical search
- Local filesystem/object directory for dummy PDFs
- JSONL exports for audit inspection
- Optional ChromaDB only as an experiment, not as the canonical domain database

The relational database should remain the source of truth for:

- Documents
- Passages
- Studies
- Claims
- Citations
- Evidence assessments
- Search sessions
- Governance decisions
- Audit events
- Access-control metadata

---

## 12. Proposed Repository Structure

```text
vyu-poc/
├── apps/
│   ├── api/
│   └── web/
├── src/vyu/
│   ├── contracts/
│   ├── connectors/
│   │   ├── pubmed/
│   │   ├── europe_pmc/
│   │   ├── clinical_trials/
│   │   ├── preprints/
│   │   └── uploaded_documents/
│   ├── ingestion/
│   ├── retrieval/
│   │   ├── bm25.py
│   │   ├── dense.py
│   │   ├── medcpt.py
│   │   ├── rrf.py
│   │   └── reranker.py
│   ├── evidence/
│   │   ├── study_classifier.py
│   │   ├── quality_assessor.py
│   │   ├── bias_assessor.py
│   │   └── contradiction_detector.py
│   ├── generation/
│   ├── citations/
│   ├── memory/
│   ├── governance/
│   ├── scoring/
│   └── audit/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── evaluations/
│   └── fixtures/
├── data/
│   ├── dummy_articles/
│   ├── dummy_pdfs/
│   └── golden_questions/
├── upstreams/
├── upstreams.yaml
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

---

## 13. Vyu Internal Contracts

Do not expose upstream-specific dictionaries throughout the codebase. Normalize all data into Vyu-owned contracts.

Example Pydantic-style models:

```python
from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class Document(BaseModel):
    document_id: str
    source: str
    title: str
    abstract: str | None = None
    full_text: str | None = None
    publication_date: date | None = None
    authors: list[str] = Field(default_factory=list)
    journal: str | None = None
    identifiers: dict[str, str] = Field(default_factory=dict)
    publication_types: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class Passage(BaseModel):
    passage_id: str
    document_id: str
    section: str | None = None
    text: str
    page: int | None = None
    start_offset: int | None = None
    end_offset: int | None = None


class EvidenceRecord(BaseModel):
    document_id: str
    study_design: str
    population: str | None = None
    intervention: str | None = None
    comparator: str | None = None
    outcomes: list[str] = Field(default_factory=list)
    sample_size: int | None = None
    bias_flags: list[str] = Field(default_factory=list)
    funding: str | None = None
    conflicts_of_interest: str | None = None
    evidence_level: str
    assessment_confidence: float
    requires_human_review: bool = False


class Citation(BaseModel):
    citation_id: str
    document_id: str
    passage_id: str
    claim_id: str
    quote_span: str
    retrieval_score: float
    source_url: str | None = None


class GovernanceRecord(BaseModel):
    run_id: str
    query: str
    source_filters: dict[str, Any]
    retrieval_configuration: dict[str, Any]
    model_configuration: dict[str, Any]
    evidence_rules_version: str
    included_documents: list[str]
    excluded_documents: list[dict[str, Any]]
    policy_events: list[dict[str, Any]]
    human_review_status: str
```

This allows upstream modules to be replaced without changing the Vyu domain model.

---

## 14. Upstream-Specific Modification Plan

### 14.1 Google PubMed MCP

#### Reuse or Adapt

- NCBI E-utilities request handling
- PubMed query construction
- Batch PMID retrieval
- Advanced date, publication-type, MeSH, and journal filters
- Related-article lookup
- Citing-article lookup
- Links to PMC and biomedical databases
- PubTator entity normalization
- Optional PMC/BigQuery full-text search

#### Required Modifications

1. Extract API clients from the MCP server layer.
2. Return Vyu `Document` and `SearchHit` objects.
3. Add:
   - Retry logic
   - Exponential backoff
   - Response caching
   - Request and response hashes
   - Retrieval timestamps
   - Audit events
4. Make BigQuery optional.
5. Add deterministic mock connectors.
6. Add source-level access and policy checks.
7. Persist the exact generated PubMed query.

#### Proposed Interface

```python
from typing import Protocol


class LiteratureConnector(Protocol):
    def search(self, query: "SearchQuery") -> list["SearchHit"]:
        ...

    def fetch(self, identifiers: list[str]) -> list[Document]:
        ...

    def related(self, document_id: str) -> list["SearchHit"]:
        ...
```

---

### 14.2 Google BioCompass

#### Reuse or Adapt

- Parallel source retrieval
- Separate quick-search and deep-research modes
- Critic/revision loop
- Research-methodology skills
- Independent state keys for parallel agents
- Evaluation suite structure
- Uploaded-file handoff patterns

#### Required Modifications

1. Wrap Google ADK behind a Vyu `AgentRuntime`, or reproduce the workflow using a provider-neutral orchestration layer.
2. Support both:
   - Gemini/Vertex
   - An OpenAI-compatible or local model provider
3. Remove image generation from the initial POC.
4. Retain these first-stage workflows:
   - PICO query construction
   - Guided evidence deep-dive
   - Evidence brief generation
   - PRISMA-style search and screening summary
5. Convert the critic output into a deterministic schema.
6. Add a maximum of two revision rounds.
7. Stop when all material claims are grounded.
8. Abstain when the evidence is insufficient.
9. Record every agent/tool transition in the audit trail.

Example critic output:

```json
{
  "citation_grounding": "pass",
  "unsupported_claims": [],
  "missing_counterevidence": [],
  "methodological_issues": [],
  "revision_required": false
}
```

---

### 14.3 gzxiong/MedRAG

#### Reuse or Adapt

- MedCPT query/article encoding
- FAISS index construction
- HNSW option
- BM25 retrieval
- Reciprocal-rank fusion
- Retriever benchmark configurations
- Retrieval scores and snippet output
- Iterative-query concepts from i-MedRAG

#### Required Modifications

1. Disable automatic corpus and embedding downloads.
2. Remove `os.system`-based operational logic.
3. Use explicit Python download/index services.
4. Validate all paths and subprocess arguments.
5. Separate:
   - Encoding
   - Index creation
   - Retrieval
   - RRF
   - Context construction
   - Generation
6. Add a local corpus constructor.
7. Add metadata filters.
8. Persist all score components.
9. Replace provider-specific model construction with the Vyu model gateway.

Example:

```python
index = MedRAGIndex.from_documents(
    documents=dummy_documents,
    retriever="MedCPT",
    index_path="./data/indexes/medcpt",
)
```

#### Required Filters

- Publication date
- Publication type
- Retraction status
- Preprint status
- Study design
- Population
- Intervention
- Language
- User/workspace access

#### Persisted Retrieval Scores

- Dense score
- BM25 score
- RRF score
- Reranker score
- Original rank
- Post-filter rank
- Final rank

---

### 14.4 Zaoqu-Liu/PubMedRAG

#### Useful Concepts to Study or Reimplement

- Question-to-PubMed query expansion
- Follow-up search detection
- Topic/session recognition
- Citation validation
- Bibliographic formatting
- Reuse of literature across related questions
- Question-driven search rather than static corpus-only RAG

#### Do Not Adopt Directly Without Review

- Monolithic orchestration
- Regex-only parsing of displayed PubMed text
- Direct OpenAI client coupling
- CSV/JSON as authoritative memory
- ChromaDB collections as canonical research records
- GPL source inside a closed/proprietary Vyu core

#### Optional Isolation Pattern

After legal review:

```text
Vyu Core ── HTTP/API ──> Separate GPL PubMed Search Service
```

The engineering boundary does not itself determine legal obligations; obtain legal advice.

---

### 14.5 RAG-Gym

#### First POC

Do not train:

- SFT agents
- DPO agents
- Reward models
- Reinforcement-learning policies

Implement an explicit research workflow with:

- Search objective
- Subquestion
- Search query
- Retrieved evidence
- Coverage assessment
- Next-action decision
- Stopping reason
- Final synthesis

#### Later Experiment

1. Export successful and unsuccessful Vyu research trajectories.
2. Label useful and unhelpful search actions.
3. Train or evaluate a planner/verifier.
4. Compare:
   - One-shot RAG
   - Fixed two-round deep-dive
   - Prompted agent
   - RAG-Gym/ReSearch-style agent
5. Adopt only if quality improves without reducing transparency.

---

## 15. Dummy Dataset

Use no real patient records and no PHI.

Create approximately **30 fictional biomedical documents**.

| Category | Count |
|---|---:|
| Randomized controlled trials | 6 |
| Systematic reviews/meta-analyses | 4 |
| Cohort or case-control studies | 5 |
| Case series/reports | 3 |
| Guidelines or consensus documents | 3 |
| Preprints | 3 |
| Deliberately conflicting studies | 4 |
| Retracted or intentionally unreliable studies | 2 |

### Suggested Fictional Topic

> Does VX-101 reduce migraine days in adults with episodic migraine compared with standard therapy?

Use a fictional intervention to avoid accidentally presenting synthetic findings as real medical advice.

### Deliberate Test Conditions

Include:

- One large positive RCT
- One small negative RCT
- One meta-analysis with high heterogeneity
- One observational study with confounding
- One unreviewed preprint
- One manufacturer-funded study
- One study underrepresenting adults over 65
- One retracted article
- Duplicate abstract records
- Similar titles with different conclusions
- An article mentioning the intervention only in the background
- A PDF with a result table
- A PDF whose figure caption qualifies or contradicts the abstract
- Missing sample-size metadata
- Conflicting outcome definitions
- Incomplete conflict-of-interest reporting

### Required Files

```text
data/dummy_articles/documents.jsonl
data/dummy_articles/passages.jsonl
data/dummy_articles/evidence_ground_truth.jsonl
data/dummy_articles/retraction_ground_truth.jsonl
data/dummy_pdfs/*.pdf
data/golden_questions/questions.jsonl
data/golden_questions/expected_documents.jsonl
data/golden_questions/expected_citations.jsonl
data/golden_questions/expected_evidence_flags.jsonl
```

---

## 16. Golden Questions

Include at least:

1. Simple fact retrieval
2. Comparative efficacy
3. Safety
4. Population-specific applicability
5. Conflicting evidence
6. Insufficient evidence
7. Exact acronym retrieval
8. Semantic matching
9. Follow-up that should reuse memory
10. Follow-up requiring a new search
11. Question whose strongest-looking paper is retracted
12. Question where the answer depends on distinguishing a preprint from peer-reviewed evidence
13. Question requiring table extraction from a PDF
14. Question testing funding/conflict-of-interest disclosure
15. Question where Vyu should explicitly recommend human review

---

## 17. End-to-End Dummy Pipeline

```text
1. Load synthetic JSONL records and PDFs
2. Parse documents and PDF structure
3. Normalize metadata
4. Identify duplicates
5. Segment into passages
6. Classify study type
7. Extract PICO and study attributes
8. Generate bias/quality indicators
9. Build BM25 index
10. Build MedCPT FAISS index
11. Run question decomposition
12. Retrieve from both indexes
13. Fuse with reciprocal-rank fusion
14. Apply metadata and governance filters
15. Rerank top passages
16. Build structured evidence context
17. Generate a grounded answer
18. Link each claim to passage-level citations
19. Validate citation entailment and identifiers
20. Detect contradictory evidence
21. Produce evidence profile
22. Calculate Trust Score components
23. Generate Governance Box
24. Save research memory
25. Save full audit trace
26. Run evaluation metrics
```

---

## 18. Evidence Grading and Bias Assessment

The POC must not represent itself as automatically completing formal:

- GRADE
- Cochrane RoB 2
- ROBINS-I
- AMSTAR 2
- QUADAS-2

Instead, call the output an **Automated Evidence Profile**.

### Automated Evidence Profile Fields

- Detected study design
- Sample size
- Intervention
- Comparator
- Population
- Outcome definitions
- Follow-up period
- Randomization indicators
- Blinding indicators
- Attrition
- Comparator appropriateness
- Confidence intervals
- Funding
- Conflicts of interest
- Retraction status
- Preprint status
- Applicability limitations
- Contradictions
- Missing-information warnings
- Assessment confidence
- Human-review requirement

Example:

```json
{
  "study_design": "randomized_controlled_trial",
  "evidence_level": "higher",
  "bias_flags": [
    "small_sample",
    "industry_funded",
    "unclear_allocation_concealment"
  ],
  "applicability_flags": [
    "participants_over_65_underrepresented"
  ],
  "assessment_confidence": 0.71,
  "formal_risk_of_bias_completed": false,
  "requires_human_review": true
}
```

---

## 19. Trust Score POC

Do not show one unexplained number. Show the total and its component breakdown.

| Component | Suggested Weight |
|---|---:|
| Claim-level citation coverage | 25% |
| Citation entailment/faithfulness | 20% |
| Evidence-design strength | 15% |
| Retrieval agreement and stability | 10% |
| Conflict handling | 10% |
| Bias/applicability completeness | 10% |
| Recency and source status | 5% |
| Audit/governance completeness | 5% |

Example:

```json
{
  "overall": 76,
  "components": {
    "citation_coverage": 92,
    "citation_faithfulness": 85,
    "evidence_strength": 70,
    "retrieval_stability": 78,
    "conflict_handling": 55,
    "bias_completeness": 63,
    "source_status": 90,
    "audit_completeness": 100
  },
  "warnings": [
    "Two studies report conflicting primary outcomes",
    "Evidence in adults over 65 is limited"
  ]
}
```

The POC Trust Score is an explainable heuristic, not a clinically validated score.

---

## 20. Governance Box

Every answer should expose a user-readable Governance Box.

Example:

```text
Sources searched:
  PubMed, local dummy PDFs

Search run:
  2026-06-13T10:30:00+05:30

Search strategy:
  Expanded PICO query + exact acronym query

Retrieved:
  26 documents

Included:
  8 documents

Excluded:
  18 documents
  - duplicates: 4
  - irrelevant population: 5
  - wrong intervention: 6
  - retracted: 1
  - insufficient content: 2

Evidence mix:
  2 RCTs
  1 meta-analysis
  3 observational studies
  1 preprint
  1 guideline

Conflicts:
  Material disagreement detected on the primary outcome

Models:
  embedding model/version
  reranker/version
  generator/version

Prompt and policy versions:
  answer_prompt_v3
  evidence_rules_v1
  governance_policy_v1

Human review:
  Required: yes
  Reason: conflicting high-priority evidence
```

The complete record should also be available as JSON.

---

## 21. Research Memory

Research memory must be scoped by:

- Tenant
- Workspace/project
- User
- Research topic
- Access-control labels
- Source permissions
- Retention policy

Memory should store:

- Previous questions
- Generated search queries
- Retrieved documents
- Included/excluded evidence
- Evidence assessments
- User annotations
- Generated reports
- Model and policy versions
- Citation graph
- Follow-up search decisions

A follow-up query should trigger one of:

```text
REUSE_EXISTING_EVIDENCE
SEARCH_NEW_EVIDENCE
REASSESS_EXISTING_EVIDENCE
GENERATE_NEW_OUTPUT_FROM_EXISTING_EVIDENCE
```

No user should receive evidence or conversational memory from another user or workspace unless access policy explicitly allows it.

---

## 22. Test Plan

### 22.1 Unit Tests

Test:

- Query expansion
- PubMed syntax generation
- Date and publication-type filters
- Identifier mapping
- Deduplication
- Retraction handling
- Passage/document linkage
- Study-design classification
- Evidence-profile rules
- Bias/applicability flags
- Trust Score calculation
- Citation formatting
- Citation validation
- Governance events
- Memory scoping
- Workspace isolation
- Policy versioning

---

### 22.2 Connector Tests

Mock all external APIs.

```python
import pytest


@pytest.fixture
def pubmed_mock_response() -> str:
    return load_fixture("pubmed_esummary_response.xml")
```

Test:

- Rate limits
- Empty results
- Invalid identifiers
- Partial batch failures
- Timeout
- Retry exhaustion
- Malformed metadata
- Duplicate records
- Retracted records
- Missing abstracts
- Missing full text
- PubTator unavailable
- Europe PMC unavailable
- ClinicalTrials.gov unavailable

---

### 22.3 Retrieval Evaluation

| Metric | Initial POC Target |
|---|---:|
| Recall@5 | >= 0.80 |
| Recall@10 | >= 0.90 |
| MRR@10 | >= 0.75 |
| nDCG@10 | >= 0.80 |
| Exact-acronym question success | 100% |
| Conflicting-evidence retrieval | Both sides in top 10 |

These are POC acceptance thresholds, not production performance claims.

---

### 22.4 Grounded-Answer Evaluation

Evaluate:

- Citation precision
- Citation recall
- Claim coverage
- Passage entailment
- Unsupported-claim rate
- Correct abstention
- Contradiction disclosure
- Evidence-strength classification
- Bias-warning accuracy
- Citation identifier validity

Suggested gates:

```text
Unsupported material claims:             < 5%
Material claims with passage citations:  > 95%
Correct insufficient-evidence abstention: > 90%
Known contradictions disclosed:          > 90%
Invalid citation identifiers:            0
```

---

### 22.5 Governance Tests

Verify:

- Every answer contains provenance.
- Retracted sources trigger warnings and policy handling.
- Preprints are not represented as peer-reviewed.
- Trust Score components are reproducible.
- Every generated claim maps to recorded evidence or is flagged.
- Uncited material claims are detected.
- Evidence-rule changes create a new version.
- Prompt/model versions are persisted.
- Memory does not cross user/workspace boundaries.
- Excluded sources retain an exclusion reason.
- Human-review decisions are logged.
- A completed run can be reconstructed from its audit record.

---

## 23. Experiment Matrix

Run every golden question against the same dummy corpus.

| Run | Retriever | Workflow | Evidence Layer | Purpose |
|---|---|---|---|---|
| A | MiniLM + FAISS | One-shot | No | Minimal baseline |
| B | MedCPT + FAISS | One-shot | No | Biomedical dense baseline |
| C | BM25 | One-shot | No | Lexical baseline |
| D | BM25 + MedCPT RRF | One-shot | Yes | Recommended baseline |
| E | Hybrid + reranker | One-shot | Yes | Retrieval quality ceiling |
| F | Hybrid + reranker | Two-step guided deep-dive | Yes | Recommended POC |
| G | Hybrid + reranker | Iterative RAG-Gym-style agent | Yes | Later experiment |

Store:

```text
retrieved_documents.json
retrieval_trace.json
answer.json
claims.json
citations.json
evidence_profile.json
trust_score.json
governance_box.json
audit_log.jsonl
evaluation.json
```

---

## 24. Phased Execution Roadmap

### Phase 0 — Repository and Licence Intake

#### Deliverables

- Exact upstream URLs
- Pinned commit SHAs
- Licence manifest
- Dependency inventory
- Model/corpus licence inventory
- Approved reuse list
- Confirmed interpretation of “Google PubMedRAG”

#### Exit Condition

No unlicensed or incompatible source has been copied into Vyu.

---

### Phase 1 — Dummy Corpus and Domain Contracts

#### Deliverables

- Synthetic JSONL corpus
- Synthetic PDFs
- Evidence ground truth
- Golden questions
- Vyu domain models
- Local database schema

#### Exit Condition

The dummy corpus can be loaded, normalized, queried, and inspected without an LLM.

---

### Phase 2 — Connector Layer

#### Deliverables

- Dummy connector
- PubMed connector
- Optional Europe PMC connector
- Optional ClinicalTrials.gov connector
- Connector mocks
- Audit logging for all searches and fetches

#### Exit Condition

All connectors return the same Vyu data contracts.

---

### Phase 3 — Retrieval Baseline

#### Deliverables

- BM25
- MedCPT + FAISS
- RRF
- Metadata filters
- Retrieval trace
- Recall/MRR/nDCG evaluation

#### Exit Condition

Hybrid retrieval meets the approved golden-set thresholds.

---

### Phase 4 — Grounded Answer Generation

#### Deliverables

- Structured context builder
- Claim extraction
- Passage-level citations
- Citation validator
- Abstention behavior
- Deterministic generation configuration

#### Exit Condition

No invalid citation identifiers and fewer than 5% unsupported material claims on the dummy evaluation set.

---

### Phase 5 — Evidence and Governance

#### Deliverables

- Study-design classifier
- Automated Evidence Profile
- Bias/applicability indicators
- Contradiction detector
- Trust Score
- Governance Box
- JSON audit export

#### Exit Condition

Every answer has a reproducible source, model, prompt, policy, and evidence trace.

---

### Phase 6 — Guided Deep-Dive and Research Memory

#### Deliverables

- PICO decomposition
- Coverage-gap detector
- Maximum two-round follow-up retrieval
- Project-scoped memory
- Search reuse decision
- Evidence brief
- Research report template
- Policy-output template

#### Exit Condition

Follow-up questions reuse prior work correctly without crossing access boundaries.

---

### Phase 7 — RAG-Gym-Style Evaluation

#### Deliverables

- Transparent iterative-search baseline
- Research trajectory dataset
- Fixed-workflow versus agent comparison
- Cost, latency, quality, and auditability report

#### Exit Condition

Agentic retrieval is adopted only if it improves difficult cases without compromising governance.

---

## 25. Recommended POC Feature Set

The first demonstrable Vyu POC should include:

1. Question entry and optional PDF upload
2. PubMed plus dummy/local-document retrieval
3. BM25 + MedCPT hybrid retrieval
4. Claim-level passage citations
5. Automatic evidence profile
6. Bias, applicability, preprint, funding, and retraction flags
7. Contradiction disclosure
8. Explainable Trust Score
9. Governance Box
10. Project-scoped research memory
11. Two-round guided literature deep-dive
12. Evidence brief generation
13. JSON audit export
14. Evaluation dashboard or report

Defer:

- Large-scale GraphRAG
- Full ontology reasoning
- Model fine-tuning
- RAG-Gym reward-model training
- Automated formal GRADE/RoB certification
- Multi-region deployment
- High-concurrency optimization
- Production SSO/RBAC integration
- Full clinical validation

---

## 26. Final Reuse Decision

### Reuse Directly or Adapt

- Google PubMed MCP API-client patterns
- Google BioCompass parallel retrieval structure
- Google BioCompass critic/revision loop
- Google BioCompass methodology skills as starting templates
- MedRAG MedCPT retrieval
- MedRAG FAISS/HNSW indexing concepts
- MedRAG BM25 and RRF concepts

### Reimplement as Vyu-Owned Code

- Domain contracts
- Canonical evidence repository
- Evidence profiling
- Bias/applicability analysis
- Claim-level citation validation
- Trust Score
- Governance Box
- Research memory
- Authorization and isolation
- Audit trail
- Provider-independent LLM gateway
- PDF ingestion
- Guided deep-dive controller
- Policy/research output templates

### Reference Only Until Cleared

- Zaoqu-Liu/PubMedRAG
- RAG-Gym/RAG-Gym
- HamsiniGupta/PubMedRAG

---

## 27. Definition of POC Success

The POC is successful when it can:

1. Ingest a synthetic biomedical corpus and PDFs.
2. Search a dummy source and live PubMed through the same connector interface.
3. Retrieve relevant evidence using hybrid lexical and biomedical semantic search.
4. Produce a concise answer whose material claims have passage-level citations.
5. Distinguish stronger and weaker study designs.
6. Surface conflicts, preprints, retractions, bias indicators, funding, and applicability limitations.
7. Abstain when evidence is insufficient.
8. Display an explainable Trust Score.
9. Display a Governance Box.
10. Reconstruct the complete run from an audit record.
11. Reuse prior research safely within the same authorized workspace.
12. Generate an evidence brief or research report from the governed evidence set.

---

## 28. Source Repositories

- Google BioCompass:  
  `https://github.com/GoogleCloudPlatform/LifeSciences/tree/main/applications/pharma-on-gemini-enterprise/biocompass-on-gemini-enterprise`

- Google PubMed MCP:  
  `https://github.com/GoogleCloudPlatform/hcls-mcp-servers/tree/main/pubmed_mcp`

- MedRAG:  
  `https://github.com/gzxiong/MedRAG`

- Zaoqu-Liu PubMedRAG:  
  `https://github.com/Zaoqu-Liu/PubMedRAG`

- RAG-Gym:  
  `https://github.com/RAG-Gym/RAG-Gym`

- HamsiniGupta PubMedRAG:  
  `https://github.com/HamsiniGupta/PubMedRAG`

---

## 29. Immediate Next Engineering Actions

```text
[ ] Create the Vyu POC repository
[ ] Add upstreams.yaml
[ ] Clone and pin upstream commits
[ ] Complete licence inventory
[ ] Create Vyu domain contracts
[ ] Generate the synthetic corpus
[ ] Implement DummyPubMedConnector
[ ] Adapt the Google PubMed client
[ ] Implement BM25 baseline
[ ] Implement MedCPT + FAISS
[ ] Implement RRF
[ ] Add retrieval evaluation
[ ] Add grounded answer schema
[ ] Add citation validation
[ ] Add automated evidence profile
[ ] Add Trust Score
[ ] Add Governance Box
[ ] Add audit export
[ ] Add two-round guided deep-dive
[ ] Run the full experiment matrix
[ ] Document POC findings and production recommendations
```
