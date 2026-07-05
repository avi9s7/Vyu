import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { formatDateTime } from "@/lib/utils/format";
import type {
  ActivityItem,
  EvidenceRecommendation,
  ReviewQueueItem
} from "@/features/dashboard/types";

export function RecentActivityList({ items }: { items: ActivityItem[] }) {
  return (
    <Card title="Recent Activity">
      <div className="space-y-4">
        {items.map((item) => (
          <div key={item.id} className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-semibold">{item.label}</p>
              <p className="mt-1 text-xs text-slate-500">
                {item.actor} · {formatDateTime(item.createdAt)}
              </p>
            </div>
            <Badge tone={item.status === "completed" ? "success" : "warning"}>
              {item.status.replace("_", " ")}
            </Badge>
          </div>
        ))}
      </div>
    </Card>
  );
}

export function RecommendedEvidenceTable({
  items
}: {
  items: EvidenceRecommendation[];
}) {
  return (
    <Card title="Recent Evidence / Recommended Sources">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead className="text-xs uppercase text-slate-500">
            <tr>
              <th className="pb-3 font-semibold">Source</th>
              <th className="pb-3 font-semibold">Type</th>
              <th className="pb-3 font-semibold">Quality</th>
              <th className="pb-3 font-semibold">Updated</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {items.map((item) => (
              <tr key={item.id}>
                <td className="py-3 pr-4 font-semibold">{item.title}</td>
                <td className="py-3 pr-4 text-slate-600">{item.sourceType}</td>
                <td className="py-3 pr-4">
                  <Badge tone={item.quality === "high" ? "success" : "warning"}>
                    {item.quality} quality
                  </Badge>
                </td>
                <td className="py-3 text-slate-600">{formatDateTime(item.updatedAt)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export function ReviewQueuePreview({ items }: { items: ReviewQueueItem[] }) {
  return (
    <Card title="Reviews Queue">
      <div className="space-y-4">
        {items.map((item) => (
          <div key={item.id} className="rounded-md border border-border p-4">
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm font-semibold">{item.title}</p>
              <Badge tone={item.priority === "high" ? "danger" : "warning"}>
                {item.priority}
              </Badge>
            </div>
            <p className="mt-2 text-xs text-slate-500">Due {item.dueDate}</p>
          </div>
        ))}
      </div>
    </Card>
  );
}
