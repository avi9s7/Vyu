# Model Safety Policy

## Purpose

This document defines the first model-safety policy baseline before Vyu introduces a model gateway. The current implementation remains deterministic and local, but the repository now has policy tests for prompt-injection signals and citation-policy export blocking.

## Prompt-Injection Policy

Retrieved text and user questions must be treated as untrusted input. Before any future model gateway receives evidence context, Vyu must scan for prompt-injection signals such as:

- requests to ignore prior instructions
- requests to reveal system or developer prompts
- tool-use instructions embedded in retrieved evidence
- exfiltration or secret-leakage instructions
- instructions to bypass policy

The implementation is `src/vyu/safety/scan_prompt_injection`. A high-risk report is not allowed for model context. Report export can persist the decision as a `prompt_injection_decision_recorded` production audit event when a storage adapter is provided.

## Citation Policy

Generated answers must pass citation policy before export:

- every material claim must have at least one citation
- every citation identifier must exist in the evidence context
- non-abstained answers must contain claims
- abstentions without claims are allowed when citation validation passes

The implementation is `src/vyu/safety/evaluate_citation_policy`. Invalid citations or uncited material claims block export. Report export can persist the decision as a `citation_policy_decision_recorded` production audit event when a storage adapter is provided.

## Current Limitations

- The prompt-injection scan is deterministic pattern matching, not a full adversarial classifier.
- The policy runs through the framework-neutral report-export API and worker adapters, but not through a deployed production API route or worker queue.
- There is no model gateway yet.
- Safety decisions are currently persisted as audit events only when the report export boundary is called with production storage.
