from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


DECISIONS = {"approve", "request_changes", "reject"}
APPROVER_ROLES = {
    "clinical_reviewer",
    "privacy_owner",
    "product_owner",
    "regulatory_reviewer",
    "security_owner",
}


def record_compliance_attestation(
    bundle_path: Path,
    attestations_path: Path,
    run_id: str,
    tenant_id: str,
    workspace_id: str,
    approver_id: str,
    approver_role: str,
    decision: str,
    comment: str,
    attested_at: str,
) -> dict[str, Any]:
    bundle_bytes = bundle_path.read_bytes()
    bundle = json.loads(bundle_bytes.decode("utf-8"))
    _validate_bundle_scope(
        bundle=bundle,
        run_id=run_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )
    if approver_role not in APPROVER_ROLES:
        raise ValueError(f"Unsupported approver role: {approver_role}")
    if decision not in DECISIONS:
        raise ValueError(f"Unsupported attestation decision: {decision}")
    bundle_status = str(bundle.get("status", "unknown"))
    if decision == "approve" and bundle_status != "ready_for_pilot_review":
        raise ValueError(
            "Approval requires bundle status ready_for_pilot_review."
        )

    record = {
        "attestation_id": (
            f"attestation-{run_id}-{approver_id}-{approver_role}"
        ),
        "attested_at": attested_at,
        "approver_id": approver_id,
        "approver_role": approver_role,
        "bundle_sha256": hashlib.sha256(bundle_bytes).hexdigest(),
        "bundle_status": bundle_status,
        "comment": comment,
        "decision": decision,
        "run_id": run_id,
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
    }
    attestations_path.parent.mkdir(parents=True, exist_ok=True)
    with attestations_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record a local approver attestation for a Vyu compliance bundle."
    )
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--attestations", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--approver-id", required=True)
    parser.add_argument("--approver-role", choices=sorted(APPROVER_ROLES), required=True)
    parser.add_argument("--decision", choices=sorted(DECISIONS), required=True)
    parser.add_argument("--comment", required=True)
    parser.add_argument("--attested-at", required=True)
    args = parser.parse_args()

    try:
        record = record_compliance_attestation(
            bundle_path=args.bundle,
            attestations_path=args.attestations,
            run_id=args.run_id,
            tenant_id=args.tenant_id,
            workspace_id=args.workspace_id,
            approver_id=args.approver_id,
            approver_role=args.approver_role,
            decision=args.decision,
            comment=args.comment,
            attested_at=args.attested_at,
        )
    except (json.JSONDecodeError, OSError, PermissionError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
