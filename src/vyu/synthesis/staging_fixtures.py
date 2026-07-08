from __future__ import annotations

"""Operational staging scenarios for Plan 7 synthesis release gates."""

PLAN7_STAGING_CHECKLIST: tuple[str, ...] = (
    "Run locked synthetic synthesis evaluation in CI (`scripts/run_synthesis_evaluation.py`).",
    "Run full staging synthesis evaluation for each provider/model/prompt/index combination.",
    "Record human adjudication for the non-PHI pilot set (`data/synthesis_evaluation/pilot_adjudication_v1.jsonl`).",
    "Force provider timeout and verify bounded retry, visible run state, and no approved answer persisted.",
    "Force provider rate limit (429) and verify retry-after handling without duplicate approved answers.",
    "Force malformed model output and verify schema-repair attempt is separately recorded or blocked.",
    "Force model refusal/safety block and verify blocked status without fallback after safety failure.",
    "Rotate provider secret version, redeploy ECS tasks, and rerun health plus synthesis smoke checks.",
    "Redeliver duplicate synthesis job message and verify idempotent answer versioning.",
    "Simulate audit persistence failure and verify terminal failure without approved answer.",
    "Bind promotion evidence to exact model snapshot, embedding model, prompt, schema, index, policy, Git SHA, and image digest.",
)

OPERATIONAL_FAILURE_SCENARIOS: tuple[dict[str, str], ...] = (
    {
        "name": "provider_timeout",
        "simulate": "GatewayTimeout",
        "expected_status": "failed",
        "expected_answer": "none",
    },
    {
        "name": "provider_rate_limit",
        "simulate": "GatewayRateLimited",
        "expected_status": "retry_or_failed",
        "expected_answer": "none",
    },
    {
        "name": "malformed_output",
        "simulate": "GatewayMalformedResponse",
        "expected_status": "failed_or_repair",
        "expected_answer": "none_or_repaired",
    },
    {
        "name": "model_refusal",
        "simulate": "GatewayPolicyBlocked",
        "expected_status": "blocked",
        "expected_answer": "none",
    },
    {
        "name": "secret_rotation",
        "simulate": "rotate_secret_and_redeploy",
        "expected_status": "healthy_after_smoke",
        "expected_answer": "n/a",
    },
    {
        "name": "duplicate_message",
        "simulate": "redeliver_job",
        "expected_status": "idempotent",
        "expected_answer": "single_version",
    },
    {
        "name": "audit_persist_failed",
        "simulate": "fail_audit",
        "expected_status": "terminal_failure",
        "expected_answer": "none",
    },
)
