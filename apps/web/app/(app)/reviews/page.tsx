import { PlaceholderSurface } from "@/components/domain/PlaceholderSurface";

export default function ReviewsPage() {
  return (
    <PlaceholderSurface
      title="Reviews"
      description="Human-in-the-loop queue for approval, rejection, escalation, and change requests."
      items={[
        "Review KPI cards",
        "Review queue",
        "Review item detail",
        "Governance snapshot",
        "Assignment card",
        "Audit trail",
        "Reviewer checklist",
        "Comments",
        "Approve / Request Changes / Escalate / Reject actions"
      ]}
    />
  );
}
