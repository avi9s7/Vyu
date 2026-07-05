# Forbidden Uses Policy

## Purpose

This policy defines uses that are not approved for the first Vyu production pilot. It applies to product behavior, APIs, reports, demos, marketing claims, and customer-facing documentation.

## Forbidden Uses

- Diagnose, treat, prevent, or manage disease for a specific patient.
- Replace independent professional, clinical, legal, regulatory, or evidence-review judgment.
- Generate patient-specific recommendations using PHI/ePHI before PHI handling is explicitly approved.
- Present deterministic POC evidence profiles as formal GRADE, RoB 2, ROBINS-I, AMSTAR 2, or clinical validation outputs.
- Hide source limitations, retraction status, preprint status, conflicts of interest, uncertainty, or missing evidence.
- Use unlicensed, blocked, retired, or unapproved source material outside its approved terms.
- Send source content, customer documents, or patient data to an unapproved model or connector provider.
- Allow cross-tenant or cross-workspace reuse of research memory, artifacts, or audit records.

## Export and Release Blocks

The system must block export or release when:

- Required human review has not been completed for a high-risk output.
- A material answer claim has no valid citation.
- The source registry marks any required source as `draft`, `blocked`, or `retired`.
- The artifact manifest lacks source records, checksums, tenant scope, or workspace scope.
- Production readiness checks fail.
- PHI/ePHI is present in a workflow that has not passed privacy, security, and regulatory review.

## Change Control

Changes to this policy require product, legal/regulatory, privacy, security, and clinical safety review before they are reflected in product behavior or customer-facing claims.
