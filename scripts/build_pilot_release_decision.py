from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


DEFAULT_REQUIRED_APPROVER_ROLES = ["privacy_owner", "security_owner"]


def build_pilot_release_decision(
    bundle_path: Path,
    attestations_path: Path,
    output_path: Path,
    run_id: str,
    tenant_id: str,
    workspace_id: str,
    required_approver_roles: list[str],
    decided_at: str,
) -> dict[str, Any]:
    bundle_bytes = bundle_path.read_bytes()
    bundle = json.loads(bundle_bytes.decode("utf-8"))
    _validate_bundle_scope(
        bundle=bundle,
        run_id=run_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )
    bundle_sha256 = hashlib.sha256(bundle_bytes).hexdigest()
    recognized_bundle_hashes = _recognized_bundle_hashes(
        bundle=bundle,
        bundle_sha256=bundle_sha256,
    )
    records = _matching_attestation_records(
        attestations_path=attestations_path,
        run_id=run_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        recognized_bundle_hashes=recognized_bundle_hashes,
    )
    latest_by_role = _latest_attestation_by_role(records)
    required_roles = sorted(set(required_approver_roles))
    blocking_reasons = _blocking_reasons(
        bundle=bundle,
        latest_by_role=latest_by_role,
        required_roles=required_roles,
    )
    approved_roles = [
        role
        for role in required_roles
        if role in latest_by_role and latest_by_role[role].get("decision") == "approve"
    ]
    missing_roles = [role for role in required_roles if role not in latest_by_role]
    payload = {
        "status": "approved_for_pilot" if not blocking_reasons else "blocked",
        "blocking_reasons": blocking_reasons,
        "decision_id": f"pilot-release-{run_id}",
        "decided_at": decided_at,
        "run_id": run_id,
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "required_approver_roles": required_roles,
        "bundle": {
            "path": str(bundle_path),
            "status": bundle.get("status"),
            "sha256": bundle_sha256,
            "attention_reasons": list(bundle.get("attention_reasons", [])),
        },
        "attestations": {
            "path": str(attestations_path),
            "record_count": len(records),
            "approved_roles": approved_roles,
            "missing_roles": missing_roles,
            "latest_by_role": latest_by_role,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def _validate_bundle_scope(
    bundle: dict[str, Any],
    run_id: str,
    tenant_id: str,
    workspace_id: str,
) -> None:
    if (
        bundle.get("run_id") != run_id
        or bundle.get("tenant_id") != tenant_id
        or bundle.get("workspace_id") != workspace_id
    ):
        raise PermissionError(
            "Compliance bundle is outside the requested tenant/workspace scope."
        )


def _recognized_bundle_hashes(
    bundle: dict[str, Any],
    bundle_sha256: str,
) -> set[str]:
    attestations = bundle.get("attestations", {})
    if not isinstance(attestations, dict):
        return {bundle_sha256}
    summary_hashes = {
        str(value)
        for value in attestations.get("bundle_sha256_values", [])
        if value
    }
    return {bundle_sha256, *summary_hashes}


def _matching_attestation_records(
    attestations_path: Path,
    run_id: str,
    tenant_id: str,
    workspace_id: str,
    recognized_bundle_hashes: set[str],
) -> list[dict[str, Any]]:
    if not attestations_path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        attestations_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        record = json.loads(line)
        if not isinstance(record, dict):
            raise ValueError(
                f"Attestation record on line {line_number} is not a JSON object."
            )
        if (
            record.get("run_id") == run_id
            and record.get("tenant_id") == tenant_id
            and record.get("workspace_id") == workspace_id
            and record.get("bundle_sha256") in recognized_bundle_hashes
        ):
            records.append(record)
    return records


def _latest_attestation_by_role(
    records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        role = str(record.get("approver_role", ""))
        if not role:
            continue
        existing = latest.get(role)
        if existing is None or str(record.get("attested_at", "")) >= str(
            existing.get("attested_at", "")
        ):
            latest[role] = record
    return dict(sorted(latest.items()))


def _blocking_reasons(
    bundle: dict[str, Any],
    latest_by_role: dict[str, dict[str, Any]],
    required_roles: list[str],
) -> list[str]:
    reasons: list[str] = []
    if bundle.get("status") != "ready_for_pilot_review":
        reasons.append("bundle_not_ready_for_pilot_review")
    for reason in bundle.get("attention_reasons", []):
        reasons.append(f"bundle_attention:{reason}")
    for role in required_roles:
        record = latest_by_role.get(role)
        if record is None:
            reasons.append(f"required_attestation_missing:{role}")
        elif record.get("decision") != "approve":
            reasons.append(f"required_attestation_not_approved:{role}")
    return sorted(set(reasons))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a local Vyu pilot release go/no-go decision summary."
    )
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--attestations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument(
        "--required-approver-role",
        action="append",
        dest="required_approver_roles",
        default=[],
    )
    parser.add_argument("--decided-at", required=True)
    args = parser.parse_args()

    required_roles = args.required_approver_roles or DEFAULT_REQUIRED_APPROVER_ROLES
    try:
        payload = build_pilot_release_decision(
            bundle_path=args.bundle,
            attestations_path=args.attestations,
            output_path=args.output,
            run_id=args.run_id,
            tenant_id=args.tenant_id,
            workspace_id=args.workspace_id,
            required_approver_roles=list(required_roles),
            decided_at=args.decided_at,
        )
    except (json.JSONDecodeError, OSError, PermissionError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
