# Phase 0 Model and Corpus Licence Inventory

Phase 0 does not download or approve model weights, embeddings, biomedical corpora, PubMed bulk data, StatPearls, textbooks, or other external datasets.

Current status:

| Asset class | Status | Phase 0 decision |
|---|---|---|
| MedCPT models or checkpoints | Not downloaded | Review model card and licence before use |
| Dense embedding indexes | Not downloaded | Build only from approved synthetic or licensed corpora |
| PubMed or PMC bulk data | Not downloaded | Use only API-accessed metadata or approved public datasets in later phases |
| StatPearls or textbook corpora | Not downloaded | Not approved for POC ingestion |
| Synthetic Vyu corpus | Not yet generated | Phase 1 will create fictional, non-PHI records |
| Uploaded PDFs | Not yet generated | Phase 1 will create fictional PDFs only |

Any future asset intake must record:

- Source URL
- Exact version or snapshot date
- Licence text and hash
- Permitted use
- Required attribution
- Redistribution restrictions
- Whether the asset can be used in demos, tests, or generated reports
