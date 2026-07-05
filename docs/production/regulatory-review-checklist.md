# Regulatory Review Checklist

## Purpose

This checklist gates production pilot changes that could affect intended use, regulatory classification, clinical safety, privacy, or customer-facing claims.

## Review Checklist

| Check | Required Evidence |
| --- | --- |
| Intended use remains literature research support. | Updated intended-use statement and feature mapping. |
| Forbidden uses are enforced. | Tests or manual review showing export and release blocks. |
| Product claims match approved inventory. | Reviewed UI, API docs, reports, and external materials. |
| No patient-specific recommendation is introduced. | Data-flow review and feature review. |
| PHI/ePHI remains out of scope or has approved controls. | Privacy/security sign-off and data classification. |
| Every source is approved for the intended use. | Source registry records and artifact manifest source metadata. |
| Users can independently inspect evidence basis. | Citations, source metadata, and governance output examples. |
| Human review is required for high-risk outputs. | Review queue or documented interim manual process. |
| Validation evidence exists for quality and safety claims. | Evaluation reports, readiness checks, and test results. |
| Incident and rollback paths are documented. | Operator runbook and incident-response procedure. |

## Required Approvers

- Product owner.
- Legal/regulatory owner.
- Clinical or evidence-methodology owner.
- Privacy owner.
- Security owner.

## Pilot Decision

A production pilot should not proceed when any checklist item lacks evidence, any required approver objects, or any readiness check fails.
