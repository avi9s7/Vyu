# Regulatory Position

## Initial Position

The first Vyu production pilot should be positioned as a governed biomedical literature research assistant for qualified professional users. It should help users search approved sources, inspect evidence, generate citation-grounded summaries, and prepare auditable research or policy-support drafts.

The first pilot should not be positioned as patient-facing software, autonomous clinical decision support, diagnosis or treatment software, or a replacement for expert review.

## Current Classification Assumption

The current repository supports a non-patient-specific literature research workflow. It uses deterministic local outputs, approved source metadata, artifact manifests, audit storage, and governance warnings. It does not currently implement production authentication, patient-specific context, PHI/ePHI workflows, LLM-based recommendations, or formal clinical validation.

## Regulatory Review Triggers

Regulatory review is required before implementing or releasing features that:

- Use patient-specific inputs, PHI/ePHI, claims records, encounters, notes, or lab results.
- Recommend diagnosis, prevention, treatment, medication, device use, or patient management.
- Hide the evidence basis from qualified users.
- Claim formal clinical decision support, clinical validation, or medical-device behavior.
- Automatically approve policy, coverage, clinical, or safety decisions without expert review.

## Required Evidence Before Pilot

- Approved intended-use and forbidden-use policy.
- Product claim inventory reviewed against user-facing language.
- Source registry approval for every live or licensed source.
- Security and privacy review for every data class.
- Human-review and export-gating rules for high-risk outputs.
- Validation evidence for retrieval, citations, evidence warnings, and governance triggers.

## Review Cadence

Review this position before any pilot release, major workflow change, new data class, new user group, new external claim, or patient-specific feature.
